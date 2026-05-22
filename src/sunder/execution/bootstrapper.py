import os
import hashlib
import docker
from docker.errors import ImageNotFound, BuildError

class Bootstrapper:
    def __init__(self):
        self.client = docker.from_env()

    def _get_file_hash(self, filepath: str) -> str:
        """Generates a SHA-256 hash of a file's contents to detect changes."""
        hasher = hashlib.sha256()
        with open(filepath, 'rb') as f:
            hasher.update(f.read())
        return hasher.hexdigest()

    def ensure_environment(self, target_path: str) -> str:
        """
        Ensures the execution environment is built from .sunder/Dockerfile. 
        Returns the image tag to be used by the Sandbox.
        """
        sunder_dir = os.path.join(target_path, ".sunder")
        dockerfile_path = os.path.join(sunder_dir, "Dockerfile")
        
        if not os.path.exists(dockerfile_path):
            raise FileNotFoundError(f"Strict Enforcement Failed: Expected `.sunder/Dockerfile` in {target_path} but it was not found.")
        
        # Hash the Dockerfile to check if we need to rebuild
        file_hash = self._get_file_hash(dockerfile_path)[:12]
        image_tag = f"sunder-sandbox:{file_hash}"

        try:
            # Check if this exact version of the image is already built locally
            self.client.images.get(image_tag)
            return image_tag
        except ImageNotFound:
            # Image doesn't exist or Dockerfile changed -> Build it
            try:
                self.client.images.build(
                    path=target_path,
                    dockerfile=".sunder/Dockerfile",
                    tag=image_tag,
                    rm=True # Clean up intermediate containers
                )
                return image_tag
            except BuildError as e:
                raise RuntimeError(f"Failed to build Sunder sandbox image: {e}")