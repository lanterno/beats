'''
Name: File Management System.
Details:
## this file should implement A manager class for reading, writing and deleting to/from files.
## Also it should convert the extracted information to the proper type.
## the operations that should be implemented are CRUD "Create - Read - Update - Delete"
Author: Zee93
'''
import json


class Manager(object):

    def create(name):
        pass

    def read(cls, fname):
        with open('data/' + fname + '.json', 'r+') as p_file:
            projects = json.load(p_file)
        return [project for project in projects]

    def update(name):
        pass

    def delete(name):
        pass
manager = Manager()
