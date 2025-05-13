#!/usr/bin/env bash

REPO_PATH=$PWD
MEMEOOORR_DB=$REPO_PATH/memeooorr.db

# Remove previous service build
if test -d memeooorr; then
  echo "Removing previous service build"
  sudo rm -r memeooorr
fi

# Push packages and fetch service
make clean

autonomy push-all

autonomy fetch --local --service dvilela/memeooorr && cd memeooorr

# Build the image
autonomy init --reset --author dvilela --remote --ipfs --ipfs-node "/dns/registry.autonolas.tech/tcp/443/https"
autonomy build-image

# Copy .env file
cp $REPO_PATH/.env .

# Copy the keys and build the deployment
cp $REPO_PATH/keys.json .

autonomy deploy build -ltm --agent-cpu-limit 4.0 --agent-memory-limit 8192 --agent-memory-request 1024

# Get the deployment directory
deployment_dir=$(ls -d abci_build_* | grep '^abci_build_' | head -n 1)

# Copy the database
if test -e $MEMEOOORR_DB; then
  echo "Copying backup database"
  cp $MEMEOOORR_DB $deployment_dir/persistent_data/logs
fi

# Copy the cookies
if test -e $TWITTER_COOKIES; then
  echo "Copying Twitter cookies"
  cp $TWITTER_COOKIES $deployment_dir/persistent_data/logs
fi

# Run the deployment
autonomy deploy run --build-dir $deployment_dir --detach
