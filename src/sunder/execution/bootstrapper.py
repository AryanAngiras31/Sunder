import os
import hashlib
import logging
import docker
from docker.errors import ImageNotFound, BuildError

# Initialize standard Python logger
logger = logging.getLogger(__name__)

class Bootstrapper:
    def __init__(self):
        self.client = docker.from_env()
        logger.debug("Initialized Bootstrapper Docker client")

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
        
        logger.debug(f"Checking for environment definition at {dockerfile_path}")
        
        if not os.path.exists(dockerfile_path):
            error_msg = (
                f"Strict Enforcement Failed: Expected `.sunder/Dockerfile` in {target_path} but it was not found. "
                f"Sunder requires explicit environment definitions to ensure safety. "
                f"Please create one in {target_path}."
            )
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)
        
        # Hash the Dockerfile to check if we need to rebuild
        file_hash = self._get_file_hash(dockerfile_path)[:12]
        image_tag = f"sunder-sandbox:{file_hash}"

        try:
            # Check if this exact version of the image is already built locally
            self.client.images.get(image_tag)
            logger.info(f"Found existing sandbox image locally: {image_tag}")
            return image_tag
        except ImageNotFound:
            # Image doesn't exist or Dockerfile changed -> Build it
            logger.info(f"Building new sandbox image: {image_tag}...")
            try:
                self.client.images.build(
                    path=target_path,
                    dockerfile=".sunder/Dockerfile",
                    tag=image_tag,
                    rm=True # Clean up intermediate containers
                )
                logger.info(f"Successfully built sandbox image: {image_tag}")
                return image_tag
            except BuildError as e:
                logger.error(f"Failed to build Sunder sandbox image: {e}")
                raise RuntimeError(f"Failed to build Sunder sandbox image: {e}")