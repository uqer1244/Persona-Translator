import os
import atexit
import streamlit as st
from core.utils import EXECUTOR

_RUNTIME_CLEANED_UP = False
_SIGNAL_HANDLERS_INSTALLED = False


def clear_mlx_cache():
    """
    Clears the Metal cache and triggers garbage collection to free unified memory.
    """
    try:
        import gc
        import mlx.core as mx

        mx.clear_cache()
        gc.collect()
    except Exception:
        pass


@st.cache_resource
def load_model_cached(model_path: str):
    """
    Loads VLM model from local folder, caching the resource and clearing memory before/after loading.
    """
    def _load():
        import mlx.core as mx
        import gc
        
        # Clear memory before loading
        mx.clear_cache()
        gc.collect()
        
        # Set cache limit to 0 to trigger immediate release of cache memory
        mx.set_cache_limit(0)
        
        from mlx_vlm import load
        model, processor = load(model_path)
        
        # Clear memory after loading
        mx.clear_cache()
        gc.collect()
        return model, processor
    
    # Run load inside single-threaded executor
    future = EXECUTOR.submit(_load)
    return future.result()


def unload_model():
    """
    Unloads the VLM model from session state, clears cached resource, and triggers cache cleaning.
    """
    st.session_state.model = None
    st.session_state.processor = None
    st.session_state.model_loaded = False
    try:
        load_model_cached.clear()
    except Exception:
        pass
    clear_mlx_cache()


def cleanup_runtime_resources(shutdown_executor: bool = False):
    """
    Cleans up all runtime resources including caching and MLX memory.
    """
    global _RUNTIME_CLEANED_UP
    if _RUNTIME_CLEANED_UP:
        return

    try:
        load_model_cached.clear()
    except Exception:
        pass

    clear_mlx_cache()

    if shutdown_executor:
        try:
            EXECUTOR.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass

    _RUNTIME_CLEANED_UP = True


def _install_shutdown_hooks():
    global _SIGNAL_HANDLERS_INSTALLED
    if _SIGNAL_HANDLERS_INSTALLED:
        return

    atexit.register(lambda: cleanup_runtime_resources(shutdown_executor=True))

    try:
        import signal
        import sys

        previous_handlers = {
            signal.SIGINT: signal.getsignal(signal.SIGINT),
            signal.SIGTERM: signal.getsignal(signal.SIGTERM),
        }

        def handle_shutdown(signum, frame):
            cleanup_runtime_resources(shutdown_executor=True)
            previous = previous_handlers.get(signum)
            if callable(previous):
                previous(signum, frame)
            elif signum == signal.SIGINT:
                raise KeyboardInterrupt
            else:
                sys.exit(0)

        signal.signal(signal.SIGINT, handle_shutdown)
        signal.signal(signal.SIGTERM, handle_shutdown)
    except Exception:
        pass

    _SIGNAL_HANDLERS_INSTALLED = True


# Automatically install hooks on load
_install_shutdown_hooks()
