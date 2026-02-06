"""
Improvement proposal routes — list, view, approve, reject proposals.
"""

import asyncio
import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from auth import verify_api_key, get_core
from models import ProposalDecision
from improvement.models import ImprovementProposal

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/proposals", tags=["proposals"])


@router.get("", dependencies=[Depends(verify_api_key)])
async def list_proposals(status: Optional[str] = None):
    """List proposals, optionally filtered by status."""
    proposals = ImprovementProposal.list_by_status(status)
    return [p.to_dict() for p in proposals]


@router.get("/{proposal_id}", dependencies=[Depends(verify_api_key)])
async def get_proposal(proposal_id: str):
    """Get a single proposal by ID."""
    proposal = ImprovementProposal.load(proposal_id)
    if not proposal:
        raise HTTPException(404, f"Proposal {proposal_id} not found")
    return proposal.to_dict()


@router.post("/{proposal_id}/approve", dependencies=[Depends(verify_api_key)])
async def approve_proposal(proposal_id: str, decision: ProposalDecision):
    """Approve a proposal and trigger execution."""
    proposal = ImprovementProposal.load(proposal_id)
    if not proposal:
        raise HTTPException(404, f"Proposal {proposal_id} not found")
    if proposal.status != "pending":
        raise HTTPException(400, f"Proposal is '{proposal.status}', not pending")

    proposal.status = "approved"
    proposal.approved_at = time.time()
    if decision.notes:
        proposal.log_step(f"Approved with notes: {decision.notes}")
    else:
        proposal.log_step("Approved by user")
    proposal.save()

    # Fire-and-forget execution
    core = get_core()
    if hasattr(core, "improvement_executor") and core.improvement_executor:
        asyncio.create_task(core.improvement_executor.execute(proposal, core))

    return {"status": "approved", "proposal_id": proposal.id}


@router.post("/{proposal_id}/reject", dependencies=[Depends(verify_api_key)])
async def reject_proposal(proposal_id: str, decision: ProposalDecision):
    """Reject a proposal."""
    proposal = ImprovementProposal.load(proposal_id)
    if not proposal:
        raise HTTPException(404, f"Proposal {proposal_id} not found")
    if proposal.status != "pending":
        raise HTTPException(400, f"Proposal is '{proposal.status}', not pending")

    proposal.status = "rejected"
    if decision.notes:
        proposal.log_step(f"Rejected with notes: {decision.notes}")
    else:
        proposal.log_step("Rejected by user")
    proposal.save()

    return {"status": "rejected", "proposal_id": proposal.id}
