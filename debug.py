import json
import os
from collections import defaultdict
from openpyxl import Workbook


def log_nurse_allocation_to_excel(solution_folders, input_base_folder, output_file):
    log_data = []
    instances = set()

    # Collect all instances from all solution folders
    for solution_folder in solution_folders:
        folder_instances = [f for f in os.listdir(
            solution_folder) if os.path.isdir(os.path.join(solution_folder, f))]
        instances.update(folder_instances)

    # Extract solution folder names for column headers
    solution_folder_names = [os.path.basename(
        folder) for folder in solution_folders]

    for instance_name in instances:
        # Extract base scenario and week file order from instance name
        base_scenario = instance_name.split('_')[0]
        week_file_order = instance_name.split('_')[2].split('-')

        # Process weeks in the specified order
        for week_index, week_file_suffix in enumerate(week_file_order):
            # Construct the input file path
            input_folder = os.path.join(input_base_folder, base_scenario)
            input_file = os.path.join(
                input_folder, f"WD-{base_scenario}-{week_file_suffix}.json")
            if not os.path.exists(input_file):
                print(f"Input file {input_file} not found!")
                continue

            # Load input data
            with open(input_file, 'r') as f:
                input_data = json.load(f)

            # Initialize nurse counts for all solutions
            solution_counts = [defaultdict(lambda: defaultdict(
                lambda: defaultdict(int))) for _ in solution_folders]

            # Compare solutions from all solution folders
            for folder_index, solution_folder in enumerate(solution_folders):
                solution_file = os.path.join(
                    solution_folder, instance_name, f"sol-week{week_index}.json")
                if not os.path.exists(solution_file):
                    print(
                        f"Solution file {solution_file} not found in {solution_folder}!")
                    continue

                # Load solution data
                with open(solution_file, 'r') as f:
                    solution_data = json.load(f)

                # Count nurses in solution
                for assignment in solution_data["assignments"]:
                    day = assignment["day"]
                    shift = assignment["shiftType"]
                    skill = assignment["skill"]
                    solution_counts[folder_index][day][shift][skill] += 1

            # Compare with input requirements
            for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]:
                for requirement in input_data["requirements"]:
                    shift = requirement["shiftType"]
                    skill = requirement["skill"]
                    required_nurses = requirement[f"requirementOn{day}"]["optimal"]

                    # Map short day names in solution to full day names in input
                    day_mapping = {
                        "Mon": "Monday", "Tue": "Tuesday", "Wed": "Wednesday",
                        "Thu": "Thursday", "Fri": "Friday", "Sat": "Saturday", "Sun": "Sunday"
                    }
                    short_day = [k for k, v in day_mapping.items()
                                 if v == day][0]

                    # Get number of nurses in all solutions
                    solution_nurses = [solution_counts[i][short_day][shift][skill] for i in range(
                        len(solution_folders))]

                    log_entry = {
                        "instance": instance_name,
                        "week": week_index,
                        "day": day,
                        "shift": shift,
                        "skill": skill,
                        "required_nurse": required_nurses,
                    }

                    # Add solution nurse counts to the log entry
                    for i, folder_name in enumerate(solution_folder_names):
                        log_entry[folder_name] = solution_nurses[i]

                    log_data.append(log_entry)

    # Write to Excel
    wb = Workbook()
    ws = wb.active
    ws.title = "Nurse Allocation Log"

    # Write header
    headers = ["instance", "week", "day", "shift",
               "skill", "required_nurse"] + solution_folder_names
    ws.append(headers)

    # Write data
    for entry in log_data:
        row = [
            entry["instance"],
            entry["week"],
            entry["day"],
            entry["shift"],
            entry["skill"],
            entry["required_nurse"],
        ] + [entry[folder_name] for folder_name in solution_folder_names]
        ws.append(row)

    # Save Excel file
    wb.save(output_file)
    print(f"Log saved to {output_file}")


# Example usage
solution_folders = [
    "solution_binomial_optilog(best)_tt_open_wbo_intel",
    "solution_binomial_new_optilog(best)_tt_open_wbo_intel"
]
input_base_folder = "/home/bach/nurse_rostering_problem/input"
output_file = "/home/bach/nurse_rostering_problem/nurse_allocation_comparison.xlsx"

log_nurse_allocation_to_excel(solution_folders, input_base_folder, output_file)
