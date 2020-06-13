import os
from pymongo import MongoClient

from app.fms import FileManager


class ProjectsMongoSynchronizer:
    def __init__(self):
        self.connection = MongoClient(os.getenv("MONGODB_URI"))
        if os.getenv("MONGODB_URI"):
            # This covers the case where DB name is provided in the URI
            self.db = self.connection.get_database()
        else:
            self.db = self.connection.ptc
        # self.users_collection = self.db['User']
        self.projects_collection = self.db['projects']

    def synchronize(self):
        projects = FileManager.read('projects')
        projects = [project for project in projects if not projects[project].get('archived')]
        for project in projects:
            self.sync_project_data(project)

    def sync_project_data(self, project_name):
        updated_logs = FileManager.read('logs/{}'.format(project_name))
        if not self.projects_collection.count_documents({"name": project_name}):
            print(f"Adding new project.. {project_name}")
            return self.projects_collection.insert({
                "name": project_name,
                "logs": updated_logs
            })
        print(f"Updating existing project.. {project_name}")
        return self.projects_collection.update({"name": project_name}, {"logs": updated_logs})