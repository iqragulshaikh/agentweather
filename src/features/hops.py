import os

import hopsworks
from dotenv import load_dotenv

load_dotenv()


def get_fs():
    project = hopsworks.login(
        api_key_value=os.getenv("HOPSWORKS_API_KEY"),
        project=os.getenv("HOPSWORKS_PROJECT"),  # your project name from .env
    )
    return project.get_feature_store()


if __name__ == "__main__":
    fs = get_fs()
    print("Connected. Feature store:", fs.name)