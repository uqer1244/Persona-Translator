import os


def load_dotenv_file(base_dir: str) -> None:
    """Load simple KEY=VALUE pairs from a project-local .env file."""
    env_path = os.path.join(base_dir, ".env")
    if not os.path.exists(env_path):
        return

    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, val = line.split("=", 1)
            os.environ[key.strip()] = val.strip().strip("'\"")
