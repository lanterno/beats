from bson.objectid import ObjectId


def serialize_from_document(document: dict) -> dict:
    document["id"] = str(document.pop("_id"))
    return document


def serialize_to_document(document: dict) -> dict:
    document["_id"] = ObjectId(document.pop("id"))
    return document
