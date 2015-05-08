import json
import simplejson


def create_project(p_name, p_estimatedtime, details=''):
    project = {
        'estimated time': p_estimatedtime,
        'details': details,
        'state': 'OFF'
    }

    with open('data/projects', 'r+') as p_file:
        projects = json.load(p_file)
        p_file.seek(0)
        p_file.truncate()
        projects.update({p_name: project})
        p_file.write(simplejson.dumps(projects, indent=4, sort_keys=True))

    print('project created.')

def start_timer_on_project(p_name):
    with open('data/projects', 'r') as p_file:
        projects = json.load(p_file)
        if projects.get(p_name) == None:
            print("We don't have a project with this name dear.")
            return 0
    with open('logs/{}'.format(p_name), 'r+'):
        pass

def stop_timer_on_project():
    with open('data/projects', 'r+') as p_file:
        pass

def execute_from_command_line(commands):
    print(commands[1:])
    if commands[0] == "createp":
        create_project(commands[1], commands[2], commands[3])

    elif commands[0] == "start":
        start_timer_on_project(commands[1:])

    elif commands[0] == "stop":
        stop_timer_on_project()

