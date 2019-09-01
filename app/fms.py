"""
Name: File Management System.
Details:
    this file should implement A manager class for reading, writing to/from files.
Author:
    Zee93
"""
import json
import simplejson

from .settings import BASE_DIR


class FileManager(object):

    """File manager to read or write to files with Json objects."""

    @staticmethod
    def read(file_name: str):
        with open(BASE_DIR + '/data/' + file_name + '.json', 'r') as p_file:
            objects = json.load(p_file)
        return objects

    @staticmethod
    def update(file_name, objects, mode='r+'):
        with open('data/' + file_name + '.json', mode) as p_file:
            p_file.seek(0)
            p_file.truncate()
            p_file.write(simplejson.dumps(objects, indent=4))
