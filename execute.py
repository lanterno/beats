from p_time import Time
from fms import FileManager
# from spread import upload_to_spread_sheet
from datetime import datetime


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


def get_status():
    settings = FileManager.read('settings')
    project_name = settings['working on']
    projects = FileManager.read('projects')
    status = projects.get(project_name)["state"]
    print('last project: {} and its status: {}'.format(project_name, status))


def start_timer_on_project(p_name, time=None):
    if time:
        now = Time(str_time=time)
    else:
        now = Time()
    # CHANGE PROJECT STATE TO ON
    projects = FileManager.read('projects')
    if not projects.get(p_name):
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


def stop_timer_on_project(time=None):
    if time:
        now = Time(str_time=time)
    else:
        now = Time()
    print("stopping Time: " + str(now))
    # GET PROJECT NAME.
    settings = FileManager.read('settings')
    p_name = settings["working on"]

    # UPDATE THE LOG.
    logs = FileManager.read('logs/{}'.format(p_name))
    if logs[-1]["end"] != "Not yet.":
        print("Error. Either you don't have a running log or the program is writing on the wrong log instance.")
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
    return [project for project in projects if not projects[project]['archived']]


def get_time_for_certain_day(p_name, date=Time.date()):
    all_logs = FileManager.read('logs/{}'.format(p_name))
    day_logs = [log for log in all_logs if log.get('date', None) == date]
    total_time = Time(sec_time=sum([Time.log_time(log).get_seconds() for log in day_logs]))
    print(total_time)
    return str(total_time)


def get_total_monthly_time_on_project(p_name, month=datetime.now().date().month, year=datetime.now().date().year):
    all_logs = FileManager.read('logs/{}'.format(p_name))
    month_logs = [log for log in all_logs if log.get('date', None) and
                  int(log.get('date').split('-')[1]) == month]  # filtered by month
    month_logs = [log for log in month_logs if log.get('date', None) and int(log.get('date').split('-')[0]) == year]
    total_time = Time(sec_time=sum([Time.log_time(log).get_seconds() for log in month_logs]))
    print(total_time)
    return str(total_time)


def sync(p_name='cube', spreadsheet='WorkSheet', month=Time.date()):
    all_logs = FileManager.read('logs/{}'.format(p_name))
    month_days = set([log['date'] for log in all_logs if log.get('date', None) and
                      int(log.get('date').split('-')[1]) == 6])
    cells_time = {}
    for day_date in month_days:
        cell_row = str(int(day_date.split('-')[2]) + 1)  # we start from 2 not 1
        cells_time.update(
            {cell_row: get_time_for_certain_day(p_name, date=day_date)})
    month = int(month.split('-')[1])
    # return upload_to_spread_sheet(p_name=p_name, spreadsheet=spreadsheet, month=month, cells_time=cells_time)
    return 0


def execute_from_command_line(commands):
    action = commands.pop(0)
    if action == "createp":
        print("Creating project...")
        create_project(*commands)

    elif action == "start":
        print("Happy coding...")
        if len(commands) == 2:
            print("Time now: " + commands[0])
            start_timer_on_project(*commands)
        else:
            print("Time now: " + str(Time()))
            start_timer_on_project(*commands)

    elif action == "stop":
        print("Stoping timer...")
        if len(commands) == 1:
            stop_timer_on_project(*commands)
        else:
            stop_timer_on_project()

    elif action == "list":
        print("your projects are: " + str(list_projects()))

    elif action == "total_time_for":
        print("Not implemented Yet.")
    elif action == "today_time_for":
        if len(commands) == 2:
            return get_time_for_certain_day(*commands)
        return get_time_for_certain_day(*commands)

    elif action == "yesterday_time_for":
        print('WARNING: not working properly.')
        if len(commands) == 2:
            return get_time_for_certain_day(*commands)
        return get_time_for_certain_day(*commands)

    elif action == "date":
        print(Time.date())
    elif action == "month_time_for":
        try:
            month = int(commands[1])
            try:
                year = int(commands[2])
                return get_total_monthly_time_on_project(commands[0], month, year)
            except:
                return get_total_monthly_time_on_project(commands[0], month)

        except:
            return get_total_monthly_time_on_project(commands[0])

    elif action == "sync":
        return sync()

    elif action == "status":
        return get_status()
    else:
        print("Wrong Command")
