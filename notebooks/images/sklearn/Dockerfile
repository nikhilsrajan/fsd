# fsd-infer-sklearn — the INFERENCE node image.
#
# Generic per DEPENDENCY FAMILY, never per model (spec 44). Since spec 44 the adapter's
# source rides inside the bundle, so this image copies NO adapter and sets NO PYTHONPATH.
# Every sklearn/joblib model you ever bundle runs on this one image; you rebuild it only
# when the fsd wheel changes or when the dependency family changes.
#
# Swap the last two deps for torch / xgboost / … and you have the next family's image.
FROM mcr.microsoft.com/azureml/openmpi4.1.0-ubuntu22.04:latest

# Same wheel as images/base — see that Dockerfile for why it lives in the build context.
# `verify_image(build_context="./images/sklearn")` reads THIS file to tell whether the
# registered image was built from a current fsd or a stale one.
COPY fsd-*.whl /tmp/

# Identical to images/base, plus the adapter's runtime deps. That is the only difference.
RUN python -m pip install --no-cache-dir "$(ls /tmp/fsd-*.whl)[azure,mpc]" scikit-learn joblib \
 && python -m pip cache purge || true
