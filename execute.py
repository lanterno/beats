def create_project(p_name, p_estimatedtime, details):
    pass

def start_timer_on_project(p_name):
    pass

def stop_timer_on_project():
    pass

def execute_from_command_line(*commands):
    if commands[0] == "createp":
        create_project(commands[1:])

    elif commands[0] == "start":
        start_timer_on_project(commands[1:])

    elif commands[0] == "stop":
        stop_timer_on_project()

