"""
ProposalExecutor — execute approved improvement proposals.

Handles: download_model, load_model, swap_model, evict_model.
Logs progress to the proposal and broadcasts updates via WebSocket.
"""

import logging
import time

from improvement.models import ImprovementProposal

logger = logging.getLogger(__name__)


class ProposalExecutor:
    """Execute approved improvement proposals."""

    async def execute(self, proposal: ImprovementProposal, core) -> None:
        """Execute a proposal — dispatches to the appropriate handler."""
        proposal.status = "executing"
        proposal.executed_at = time.time()
        proposal.log_step("Execution started")
        proposal.save()

        await core.broadcast({
            "type": "proposal_progress",
            "proposal_id": proposal.id,
            "status": "executing",
            "message": "Execution started",
        })

        try:
            solution_type = proposal.solution_type

            if solution_type == "download_model":
                await self._execute_download(proposal, core)
            elif solution_type == "load_model":
                await self._execute_load(proposal, core)
            elif solution_type == "swap_model":
                await self._execute_swap(proposal, core)
            elif solution_type == "evict_model":
                await self._execute_evict(proposal, core)
            else:
                raise ValueError(f"Unknown solution_type: {solution_type}")

            proposal.status = "completed"
            proposal.completed_at = time.time()
            proposal.log_step("Execution completed successfully")
            proposal.save()

            await core.broadcast({
                "type": "proposal_progress",
                "proposal_id": proposal.id,
                "status": "completed",
                "message": "Proposal executed successfully",
            })

            logger.info("[Executor] Proposal %s completed: %s", proposal.id, proposal.solution_summary)

        except Exception as e:
            proposal.status = "failed"
            proposal.error = str(e)
            proposal.completed_at = time.time()
            proposal.log_step(f"Execution failed: {e}")
            proposal.save()

            await core.broadcast({
                "type": "proposal_progress",
                "proposal_id": proposal.id,
                "status": "failed",
                "message": str(e),
            })

            logger.error("[Executor] Proposal %s failed: %s", proposal.id, e)

    async def _execute_download(self, proposal: ImprovementProposal, core):
        """Download a model via the inference backend."""
        model_id = proposal.solution_details.get("model_id") or proposal.solution_details.get("model_key", "")
        if not model_id:
            raise ValueError("No model_id in solution_details")

        proposal.log_step(f"Downloading model: {model_id}")
        proposal.save()

        await core.broadcast({
            "type": "proposal_progress",
            "proposal_id": proposal.id,
            "status": "executing",
            "message": f"Downloading model: {model_id}",
        })

        success = await core.inference.download_model(model_id)
        if not success:
            raise RuntimeError(f"Download failed for model {model_id}")

        proposal.log_step(f"Download complete: {model_id}")
        proposal.result = f"Model {model_id} downloaded successfully"

        # Also load if it's an always-loaded model
        model_key = proposal.solution_details.get("model_key", "")
        if model_key and core.model_manager:
            proposal.log_step(f"Loading model: {model_key}")
            await core.model_manager.ensure_loaded(model_key)
            proposal.log_step(f"Model loaded: {model_key}")

    async def _execute_load(self, proposal: ImprovementProposal, core):
        """Load a model via the model manager."""
        model_key = proposal.solution_details.get("model_key", "")
        if not model_key:
            raise ValueError("No model_key in solution_details")

        proposal.log_step(f"Loading model: {model_key}")
        proposal.save()

        if core.model_manager:
            success = await core.model_manager.ensure_loaded(model_key)
        else:
            from config import MODELS
            model_id = MODELS.get(model_key, model_key)
            success = await core.inference.load_model(model_id)

        if not success:
            raise RuntimeError(f"Failed to load model {model_key}")

        proposal.log_step(f"Model loaded: {model_key}")
        proposal.result = f"Model {model_key} loaded successfully"

    async def _execute_swap(self, proposal: ImprovementProposal, core):
        """Swap one model for another: unload old, load new."""
        old_key = proposal.solution_details.get("old_model_key", "")
        new_key = proposal.solution_details.get("model_key", "")
        new_model_id = proposal.solution_details.get("model_id", "")

        if not new_key and not new_model_id:
            raise ValueError("No target model specified in solution_details")

        # Unload old model if specified
        if old_key and core.model_manager:
            proposal.log_step(f"Unloading old model: {old_key}")
            proposal.save()
            await core.model_manager.force_unload(old_key)
            proposal.log_step(f"Old model unloaded: {old_key}")

        # Download new model if needed
        if new_model_id:
            proposal.log_step(f"Ensuring new model available: {new_model_id}")
            proposal.save()
            inventory = await core.inference.discover_models()
            if new_model_id not in inventory:
                await core.inference.download_model(new_model_id)
                proposal.log_step(f"Downloaded: {new_model_id}")

        # Load new model
        if new_key and core.model_manager:
            proposal.log_step(f"Loading new model: {new_key}")
            await core.model_manager.ensure_loaded(new_key)
            proposal.log_step(f"New model loaded: {new_key}")

        proposal.result = f"Model swap complete: {old_key or 'none'} -> {new_key or new_model_id}"

    async def _execute_evict(self, proposal: ImprovementProposal, core):
        """Evict on-demand models to free resources."""
        if not core.model_manager:
            raise RuntimeError("ModelManager not available")

        model_key = proposal.solution_details.get("model_key", "")
        proposal.log_step("Evicting on-demand models to free resources")
        proposal.save()

        # Force-unload on-demand models that aren't referenced
        status = core.model_manager.get_status()
        evicted = []
        for mk in status.get("loaded", []):
            if mk not in core.model_manager._always_loaded:
                refs = core.model_manager.get_ref_count(mk)
                if refs == 0:
                    await core.model_manager.force_unload(mk)
                    evicted.append(mk)
                    proposal.log_step(f"Evicted: {mk}")

        # Retry loading the target model if specified
        if model_key:
            proposal.log_step(f"Retrying load: {model_key}")
            success = await core.model_manager.ensure_loaded(model_key)
            if not success:
                raise RuntimeError(f"Still cannot load {model_key} after eviction")
            proposal.log_step(f"Successfully loaded {model_key} after eviction")

        proposal.result = f"Evicted {len(evicted)} models: {', '.join(evicted) or 'none'}. Target: {model_key or 'N/A'}"
