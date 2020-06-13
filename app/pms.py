"""
Name: Project Management System.
Details:
## this file should implement A manager class for reading, writing and deleting to/from projects file.
## Also it should convert the extracted information to the proper type.
## the operations that should be implemented are CRUD "Create - Read - Update - Delete"
Author: Zee93
"""
import json
import simplejson

from .settings import BASE_DIR


class ProjectsManager:

    @staticmethod
    def read(file_name='projects'):
        with open(BASE_DIR + '/data/' + file_name + '.json', 'r+') as projects_file:
            projects = json.load(projects_file)
        return projects

    @staticmethod
    def update(projects, file_name='projects'):
        with open(BASE_DIR + '/data/' + file_name + '.json', 'r+') as projects_file:
            projects_file.seek(0)
            projects_file.truncate()
            projects_file.write(simplejson.dumps(projects, indent=4))
