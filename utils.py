from datetime import time
import os


def add_time(t1: time, hour: int, min: int) -> time:
    m = t1.minute + min
    return time(hour=t1.hour + hour + int(m / 60), minute=m % 60)


def get_diff_time(t1: time, t2: time) -> tuple[int, int]:
    if t2.hour < t1.hour:
        raise ValueError
    if t2.hour == t1.hour and t2.minute <= t1.minute:
        raise ValueError
    return (t2.hour - t1.hour, t2.minute - t1.minute)


def num_secs(timestamp: str) -> int:
    fields = timestamp.split(":")
    return int(fields[0]) * 3600 + int(fields[1]) * 60


def get_s3_object_keys(s3_client, prefix: str) -> list[str]:
    s3_bucket = os.getenv("S3_BUCKET")
    contents = s3_client.list_objects(Bucket=s3_bucket, Prefix=prefix).get(
        "Contents", []
    )
    return [c["Key"] for c in contents]
