# fsd-aml-env — the GENERAL-PURPOSE node image.
#
# Used by every AML job that is not inference: download shards, datacube builds,
# create_training_data's flatten. Nothing model-specific belongs in here.
#
# Base image proven on this cluster by spec 36 — don't swap it casually.
FROM mcr.microsoft.com/azureml/openmpi4.1.0-ubuntu22.04:latest

# The fsd wheel, built from YOUR working tree by 00_build_images.ipynb (step 3).
# This is the whole reason a wheel sits in this folder: it is the thing being
# installed into the image. It has nothing to do with bundling a model.
COPY fsd-*.whl /tmp/

# [azure] -> adlfs + azure-identity + azure-keyvault-secrets: blob I/O through the
#            storage seam, managed-identity auth, Key Vault creds on the node.
# [mpc]   -> planetary-computer: signs asset hrefs on the node, right before transfer.
# NOT [aml]  -> azure-ai-ml is the DRIVER-side dispatch SDK. The node never submits jobs.
# NOT [grid] -> s2/s2cell tile the ROI into grid cells, which happens on the driver
#               before any job exists. The node only reads the cells it is handed.
RUN python -m pip install --no-cache-dir "$(ls /tmp/fsd-*.whl)[azure,mpc]" \
 && python -m pip cache purge || true
