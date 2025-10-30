
from bson.objectid import ObjectId


def serialize_from_document(document: dict) -> dict:
    """Convert MongoDB document _id to string id in-place."""
    if "_id" in document:
        document["id"] = str(document.pop("_id"))
    return document


def serialize_to_document(document: dict) -> dict:
    """Convert API document id to MongoDB ObjectId in-place."""
    if "id" in document:
        document["_id"] = ObjectId(document.pop("id"))
    return document
