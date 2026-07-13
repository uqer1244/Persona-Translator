import os

from core.env import load_dotenv_file

load_dotenv_file(os.path.dirname(__file__))

import core.patches  # noqa: F401
from core.session_state import initialize_session_state, sync_project_from_session
from ui.app_shell import configure_page, render_app


def main() -> None:
    configure_page()
    initialize_session_state()
    sync_project_from_session()
    render_app()


if __name__ == "__main__":
    main()
