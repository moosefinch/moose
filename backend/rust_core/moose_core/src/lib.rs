//! Moose Core - High-performance Rust backend for Moose AI

use pyo3::prelude::*;

pub mod episodic;
pub mod messages;
pub mod router;
pub mod scheduler;
pub mod vector;
pub mod workspace;

#[pymodule]
fn moose_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<vector::VectorMemory>()?;
    m.add_class::<episodic::EpisodicMemory>()?;
    m.add_class::<messages::MessageBus>()?;
    m.add_class::<workspace::SharedWorkspace>()?;
    m.add_class::<scheduler::Scheduler>()?;
    m.add_class::<router::InferenceRouter>()?;
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    Ok(())
}
