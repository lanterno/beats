from p_time import Time
from fms import FileManager


def create_project(p_name, details='', p_estimatedtime="Unknown"):
    project = {
        'estimated time': p_estimatedtime,
        'details': details,
        'state': 'OFF',
        'total_spent_time': "0:0:0"
    }

    projects = FileManager.read('projects')
    projects.update({p_name: project})
    FileManager.update('projects', projects)

    FileManager.update('logs/{}'.format(p_name), [], mode='w')

    print('project created.')


def start_timer_on_project(p_name):
    now = Time()
    # CHANGE PROJECT STATE TO ON
    projects = FileManager.read('projects')
    if projects.get(p_name) == None:
        print("We don't have a project with this name dear.")
        return 0
    projects.get(p_name)["state"] = "ON"
    FileManager.update('projects', projects)

    # START LOG TIME
    logs = FileManager.read('logs/{}'.format(p_name))
    logs.append({'start': str(now), 'end': 'Not yet.', 'date': Time.date()})
    FileManager.update('logs/{}'.format(p_name), logs)

    # put the project in workon in the settings file.
    settings = FileManager.read('settings')
    settings["working on"] = p_name
    FileManager.update('settings', settings)


def stop_timer_on_project():
    now = Time()
    # GET PROJECT NAME.
    settings = FileManager.read('settings')
    p_name = settings["working on"]

    # UPDATE THE LOG.
    logs = FileManager.read('logs/{}'.format(p_name))
    if logs[-1]["end"] != "Not yet.":
        print("Error. Either you don't have a running log or\
              the program is writing on the wrong log instance.")
        return 0
    logs[-1]["end"] = str(now)
    FileManager.update('logs/{}'.format(p_name), logs)
    start = Time()
    start.set_string(logs[-1]["start"])
    now.minues(start)
    elapsed_time = now

    # CHANGE PROJECT STATE TO OFF.
    projects = FileManager.read('projects')
    workon_project = projects.get(p_name)
    workon_project["state"] = "OFF"

    # ADD THE ELAPSED TIME.
    total_time = Time(str_time=workon_project["total_spent_time"])
    total_time.add_time(elapsed_time)
    print("Elapsed time: " + str(elapsed_time))
    workon_project["total_spent_time"] = str(total_time)
    projects[p_name] = workon_project
    FileManager.update('projects', projects)


def list_projects():
    projects = FileManager.read('projects')
    return [project for project in projects]


def get_time_for_certain_day(p_name, date=Time.date()):
    logs = FileManager.read('logs/{}'.format(p_name))
    logs = [log for log in logs if log.get('date', None) == date]
    total_time = Time(sec_time=sum([Time.log_time(log).get_seconds() for log in logs]))
    print(total_time)


def execute_from_command_line(commands):
    if commands[0] == "createp":
        print("Creating project...")
        create_project(commands[1], commands[2], commands[3])

    elif commands[0] == "start":
        print("Happy coding...")
        print("Time now: " + str(Time()))
        start_timer_on_project(commands[1])

    elif commands[0] == "stop":
        print("Stoping timer...")
        print("Time now: " + str(Time()))
        stop_timer_on_project()

    elif commands[0] == "list":
        print("your projects are: " + str(list_projects()))

    elif commands[0] == "total_time_for":
        print("Not implemented Yet.")
    elif commands[0] == "today_time_for":
        if len(commands) == 3:
            return get_time_for_certain_day(commands[1], commands[2])
        return get_time_for_certain_day(commands[1])

    elif commands[0] == "yesterday_time_for":
        if len(commands) == 3:
            return get_time_for_certain_day(commands[1], commands[2])
        return get_time_for_certain_day(commands[1])

    elif commands[0] == "date":
        print(Time.date())
    else:
        print("Wrong Command")
