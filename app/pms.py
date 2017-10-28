'''
Name: Project Management System.
Details:
## this file should implement A manager class for reading, writing and deleting to/from projects file.
## Also it should convert the extracted information to the proper type.
## the operations that should be implemented are CRUD "Create - Read - Update - Delete"
Author: Zee93
'''
import json
import simplejson

from .settings import BASE_DIR


class ProjectsManager(object):

    def create(name):
        pass

    def read(cls, fname='projects'):
        with open(BASE_DIR + '/data/' + fname + '.json', 'r+') as p_file:
            projects = json.load(p_file)
        return projects

    def update(projects, fname='projects'):
        with open(BASE_DIR + '/data/' + fname + '.json', 'r+') as p_file:
            p_file.seek(0)
            p_file.truncate()
            p_file.write(simplejson.dumps(projects, indent=4))

    def delete(name):
        pass

manager = ProjectsManager()
