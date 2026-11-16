import pandas as pd
def prepare(df):
    df = df.copy().rename(columns={"timestamp": "ts"})
    df["ts"] = pd.to_datetime(df["ts"], utc=True).astype("datetime64[us, UTC]")
    for c in df.columns:
        if c == "ts" or df[c].dtype == bool:
            continue
        df[c] = df[c].astype("float64")
    return df


def write_group(fs, name, df, description, version=2):
    fg = fs.get_or_create_feature_group(
        name=name,
        version=version,
        primary_key=["ts"],
        event_time="ts",
        description=description,
        online_enabled=False,
        stream=True,
    )
    fg.insert(prepare(df), write_options={"wait_for_job": True})
    return fg