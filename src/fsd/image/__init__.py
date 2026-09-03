"""`fsd.image` — declarative AML node-image definitions and a registry for them.

An `ImageDefinition` is data, not a Dockerfile: what base image, what fsd reference, what
extras. It renders a Dockerfile and a build context; it never builds one and never touches
the network. Building is `fsd.aml`'s job -- backend-specific, and the only module in this
area that is.
"""

from fsd.image.definition import ImageDefinition

__all__ = ["ImageDefinition"]
