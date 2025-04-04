import os
import re
import pandas as pd


def extract_clauses(file_path):
    with open(file_path, 'r') as file:
        content = file.read()

        status = 'SAT'
        if "No valid solution found in the output." in content:
            status = 'UNSAT'

        soft_clauses_match = re.search(
            r'Number of soft clauses:\s*(\d+)', content)
        hard_clauses_match = re.search(
            r'Number of hard clauses:\s*(\d+)', content)
        variables_match = re.search(
            r'Total number of variables:\s*(\d+)', content)
        timeout_match = re.search(r'Timeout:\s*(\d+)', content)
        total_cost_match = re.search(r'Total cost:\s*(\d+)', content)

        soft_clauses = int(soft_clauses_match.group(1)
                           ) if soft_clauses_match else 0
        hard_clauses = int(hard_clauses_match.group(1)
                           ) if hard_clauses_match else 0
        variables = int(variables_match.group(1)) if variables_match else 0
        timeout = int(timeout_match.group(1)) if timeout_match else 0
        total_cost = int(total_cost_match.group(1)) if total_cost_match else 0

        return soft_clauses, hard_clauses, variables, timeout, total_cost, status


def extract_solution_status(solution_folder):
    log_file_path = os.path.join(solution_folder, 'log.txt')
    if not os.path.exists(log_file_path):
        return 'UNKNOWN'

    with open(log_file_path, 'r') as file:
        for line in file:
            if line.startswith('s'):
                if 'OPTIMUM' in line:
                    return 'OPTIMUM'
                elif 'SATISFIABLE' in line:
                    return 'SATISFIABLE'
                elif 'UNKNOWN' in line:
                    return 'TIMEOUT'
    return 'UNKNOWN'


def extract_to_xlsx(output_folder, solution_folder):
    results = []

    # Get sorted list of files
    files = sorted([f for f in os.listdir(
        output_folder) if f.endswith('.txt')])

    for filename in files:
        file_path = os.path.join(output_folder, filename)
        soft_clauses, hard_clauses, variables, timeout, total_cost, status = extract_clauses(
            file_path)
        instance_name = filename[:-4]  # Remove the .txt extension

        # Extract solution status
        solution_status = extract_solution_status(
            os.path.join(solution_folder, instance_name))

        results.append({
            'Instance': instance_name,
            'Soft Clauses': soft_clauses,
            'Hard Clauses': hard_clauses,
            'Variables': variables,
            'Timeout(s)': timeout,
            'Total Cost': total_cost,
            'Status': status,
            'Solution Status': solution_status
        })

    # Convert results to a DataFrame
    df = pd.DataFrame(results)

    # Write DataFrame to an Excel file
    output_excel_file = f'statistic/{output_folder}.xlsx'
    os.makedirs(os.path.dirname(output_excel_file), exist_ok=True)
    df.to_excel(output_excel_file, index=False)

    print(f"Data written to {output_excel_file}")


if __name__ == "__main__":
    # extract_to_xlsx('output_for_SC', 'solution')
    extract_to_xlsx('binomial_bdd_tt_open_wbo', 'solution')
    # extract_to_xlsx('new_output_for_binomial', 'solution')
