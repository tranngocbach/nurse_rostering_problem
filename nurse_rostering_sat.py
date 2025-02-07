# nurse_rostering_sat.py

import os
import json
import argparse
import random
from itertools import combinations
from pypblib import pblib
from pypblib.pblib import PBConfig, Pb2cnf
from pysat.solvers import Glucose3
from pysat.formula import WCNF
from pysat.examples.rc2 import RC2


# Dictionary lưu biến và chỉ số SAT
variable_dict = {}
reverse_variable_dict = {}
counter = 1
max_var_cmin = 0

# Tạo biến chỉ khi cần


def get_variable(name):
    global counter
    if name not in variable_dict:
        variable_dict[name] = counter
        reverse_variable_dict[counter] = name
        counter += 1
    return variable_dict[name]

# Hàm đọc dữ liệu từ các file JSON


def load_data(scenario_file, history_file, weekday_file):
    with open(scenario_file) as f:
        scenario = json.load(f)
    with open(history_file) as f:
        history = json.load(f)
    with open(weekday_file) as f:
        weekday = json.load(f)

    N = len(scenario['nurses'])
    D = 7  # Giả định mỗi tuần có 7 ngày
    S = [shift['id'] for shift in scenario['shiftTypes']]
    SK = scenario['skills']
    W = scenario['numberOfWeeks']
    nurse_skills = {n: nurse['skills']
                    for n, nurse in enumerate(scenario['nurses'])}
    forbidden_shifts = scenario['forbiddenShiftTypeSuccessions']
    shift_off_requests = weekday.get('shiftOffRequests', [])

    # Map nurse names to indices
    nurse_name_to_index = {nurse['id']: n for n,
                           nurse in enumerate(scenario['nurses'])}

    # Map nurses index to their contracts
    nurse_contracts = {n: nurse['contract']
                       for n, nurse in enumerate(scenario['nurses'])}
    # list of contracts
    contracts = {contract['id']: contract
                 for contract in scenario['contracts']}

    # Load history data
    nurse_history = {nurse['nurse']
        : nurse for nurse in history['nurseHistory']}

    return scenario, history, weekday, N, D, S, SK, W, nurse_skills, forbidden_shifts, shift_off_requests, nurse_name_to_index, nurse_contracts, contracts, nurse_history
# Hàm lấy giá trị Cmin từ dữ liệu weekday


def get_Cmin(weekday, d, s, sk):
    day_mapping = {0: 'Monday', 1: 'Tuesday', 2: 'Wednesday',
                   3: 'Thursday', 4: 'Friday', 5: 'Saturday', 6: 'Sunday'}
    day = day_mapping.get(d, 'Monday')

    for req in weekday.get('requirements', []):
        if req['shiftType'] == s and req['skill'] == sk:
            return req.get(f'requirementOn{day}', {}).get('minimum', 0)
    return 0

# Hàm lấy giá trị Copt từ dữ liệu weekday


def get_Copt(weekday, d, s, sk):
    day_mapping = {0: 'Monday', 1: 'Tuesday', 2: 'Wednesday',
                   3: 'Thursday', 4: 'Friday', 5: 'Saturday', 6: 'Sunday'}
    day = day_mapping.get(d, 'Monday')

    for req in weekday.get('requirements', []):
        if req['shiftType'] == s and req['skill'] == sk:
            return req.get(f'requirementOn{day}', {}).get('optimal', 0)
    return 0

# H1: Mỗi y tá chỉ làm 1 ca mỗi ngày (chỉ kiểm tra các kỹ năng phù hợp)


def constraint_H1(N, D, S, SK, nurse_skills):
    clauses = []
    for n in range(N):
        for d in range(D):
            shifts = [get_variable(f"x_{n}_{d}_{s}_{sk}")
                      for s in S for sk in nurse_skills.get(n, [])]
            for (s1, s2) in combinations(shifts, 2):
                clauses.append(f"-{s1} -{s2} 0")
    return clauses

# H2: Đảm bảo số lượng y tá tối thiểu cho mỗi ca (BDD Encoding)
# def constraint_H2(N, D, S, SK, weekday, nurse_skills):
    clauses = []
    config = PBConfig()
    config.set_PB_Encoder(pblib.PB_BDD)
    pb2 = Pb2cnf(config)
    for d in range(D):
        for s in S:
            for sk in SK:
                Cmin = get_Cmin(weekday, d, s, sk)
                nurses = [get_variable(f"x_{n}_{d}_{s}_{sk}") for n in range(
                    N) if sk in nurse_skills.get(n, [])]

                if Cmin > 0 and len(nurses) >= Cmin:
                    formula = []

                    max_var = pb2.encode_at_least_k(
                        nurses, Cmin, formula, len(variable_dict))
                    for clause in formula:
                        clauses.append(" ".join(map(str, clause)) + " 0")
    return clauses

# H3: Cấm các ca làm việc không hợp lệ liên tiếp nhau


def constraint_H3(N, D, S, SK, nurse_skills, forbidden_shifts):
    clauses = []
    for n in range(N):
        for d in range(D - 1):
            for forbidden_shift in forbidden_shifts:
                s1 = forbidden_shift['precedingShiftType']
                for s2 in forbidden_shift['succeedingShiftTypes']:
                    for sk1 in nurse_skills.get(n, []):
                        for sk2 in nurse_skills.get(n, []):
                            var1 = get_variable(f"x_{n}_{d}_{s1}_{sk1}")
                            var2 = get_variable(f"x_{n}_{d+1}_{s2}_{sk2}")
                            clauses.append(f"-{var1} -{var2} 0")
    return clauses

# H4: Chỉ y tá có kỹ năng phù hợp mới được phân công


# def constraint_H4(N, D, S, SK, nurse_skills):
    clauses = []
    for n in range(N):
        for d in range(D):
            for s in S:
                for sk in SK:
                    if sk not in nurse_skills.get(n, []):
                        var = get_variable(f"x_{n}_{d}_{s}_{sk}")
                        clauses.append(f"-{var} 0")
    return clause

# H2 & S1: Minimum & Optimum


def constraint_H2(N, D, S, SK, weekday, nurse_skills, penalty_weight=30):
    hard_clauses = []
    soft_clauses = []
    config = PBConfig()
    config.set_PB_Encoder(pblib.PB_BDD)
    pb2 = Pb2cnf(config)

    for d in range(D):
        for s in S:
            for sk in SK:
                Cmin = get_Cmin(weekday, d, s, sk)
                # Copt = get_Copt(weekday, d, s, sk)
                nurses = [get_variable(f"x_{n}_{d}_{s}_{sk}") for n in range(
                    N) if sk in nurse_skills.get(n, [])]

                # Ensure at least Cmin nurses are assigned (hard constraint)
                if Cmin > 0 and len(nurses) >= Cmin:
                    formula = []
                    global max_var_cmin
                    max_var_cmin = pb2.encode_at_least_k(
                        nurses, Cmin, formula, len(variable_dict))
                    for clause in formula:
                        hard_clauses.append(" ".join(map(str, clause)) + " 0")

                # Penalize each missing nurse below Copt (soft constraint)
                # if Copt > 0:
                #     formula = []
                #     max_var_copt = pb2.encode_at_least_k(
                #         nurses, Copt, formula, max_var_cmin)
                #     for clause in formula:
                #         soft_clauses.append(
                #             (penalty_weight, " ".join(map(str, clause)) + " 0"))

    return hard_clauses

# Hàm giải bài toán bằng SAT Solver (Glucose)


# def solve_sat(clauses):
    solver = Glucose3()
    for clause in clauses:
        solver.add_clause(
            list(map(int, clause.strip().split()[:-1])))  # Bỏ ký tự '0'

    if solver.solve():
        model = solver.get_model()
        return [reverse_variable_dict[abs(var)] for var in model if var > 0]
    else:
        return None


# S1.
def constraint_S1(N, D, S, SK, weekday, nurse_skills, penalty_weight=30):
    soft_clauses = []
    config = PBConfig()
    config.set_PB_Encoder(pblib.PB_BDD)
    pb2 = Pb2cnf(config)

    for d in range(D):
        for s in S:
            for sk in SK:
                Copt = get_Copt(weekday, d, s, sk)
                nurses = [get_variable(f"x_{n}_{d}_{s}_{sk}") for n in range(
                    N) if sk in nurse_skills.get(n, [])]

                # Penalize each missing nurse below Copt (soft constraint)
                if Copt > 0:
                    formula = []
                    print(max_var_cmin)
                    max_var_copt = pb2.encode_at_least_k(
                        nurses, Copt, formula, max_var_cmin)
                    for clause in formula:
                        soft_clauses.append(
                            (penalty_weight, " ".join(map(str, clause)) + " 0"))

    return soft_clauses

# S4. Preferences(10)


def constraint_S4_SOR(N, D, S, SK, nurse_skills, shift_off_requests, nurse_name_to_index, penalty_weight=10):
    soft_clauses = []
    day_mapping = {0: 'Monday', 1: 'Tuesday', 2: 'Wednesday',
                   3: 'Thursday', 4: 'Friday', 5: 'Saturday', 6: 'Sunday'}

    for request in shift_off_requests:
        nurse_name = request['nurse']
        shift_type = request['shiftType']
        day = request['day']

        # Find the nurse index
        nurse_index = nurse_name_to_index.get(nurse_name, None)
        if nurse_index is None:
            continue

        # Find the day index
        day_index = next(
            (d for d, day_name in day_mapping.items() if day_name == day), None)
        if day_index is None:
            continue

        # Generate soft clauses for the shift off request
        for sk in nurse_skills.get(nurse_index, []):
            if shift_type == "Any":
                for s in S:
                    var = get_variable(f"x_{nurse_index}_{day_index}_{s}_{sk}")
                    soft_clauses.append((penalty_weight, f"-{var} 0"))
            else:
                var = get_variable(
                    f"x_{nurse_index}_{day_index}_{shift_type}_{sk}")
                soft_clauses.append((penalty_weight, f"-{var} 0"))

    return soft_clauses

# S5: Complete Weekend


def constraint_S5(N, D, S, nurse_skills, nurse_contracts, contracts, penalty_weight=10):
    soft_clauses = []
    weekends = [(5, 6)]  # Saturday (5) and Sunday (6)

    for n in range(N):
        contract_id = nurse_contracts[n]
        contract = contracts[contract_id]

        if contract.get('completeWeekends', 0) == 1:
            for d1, d2 in weekends:
                # p_{n, d} = 1 if the nurse works on any shift during the day
                p_d1_vars = [get_variable(f"x_{n}_{d1}_{s}_{sk}")
                             for s in S for sk in nurse_skills.get(n, [])]
                p_d2_vars = [get_variable(f"x_{n}_{d2}_{s}_{sk}")
                             for s in S for sk in nurse_skills.get(n, [])]

                # Add clauses to ensure the nurse works both days or none
                for p_d1 in p_d1_vars:
                    for p_d2 in p_d2_vars:
                        # If the nurse must work both days or none
                        # If the nurse works on Saturday, they must work on Sunday and vice versa
                        soft_clauses.append(
                            (penalty_weight, f"-{p_d1} {p_d2} 0"))
                        soft_clauses.append(
                            (penalty_weight, f"{p_d1} -{p_d2} 0"))

    return soft_clauses


# Hàm giải bài toán bằng SAT Solver (Glucose)
def solve_sat(clauses):
    solver = Glucose3()
    for clause in clauses:
        solver.add_clause(
            list(map(int, clause.strip().split()[:-1])))  # Bỏ ký tự '0'

    if solver.solve():
        model = solver.get_model()
        return [reverse_variable_dict[abs(var)] for var in model if var > 0]
# Hàm giải bài toán bằng MaxSAT Solver (RC2)


def solve_maxsat(hard_clauses, soft_clauses):
    wcnf = WCNF()

    # Add hard constraints
    for clause in hard_clauses:
        wcnf.append([int(lit) for lit in clause.split() if lit != '0'])

    # Add soft constraints with penalty
    for weight, clause in soft_clauses:
        wcnf.append([int(lit)
                    for lit in clause.split() if lit != '0'], weight=weight)

    solver = RC2(wcnf)
    solution = solver.compute()

    if solution:
        return [reverse_variable_dict[abs(var)] for var in solution if var > 0]
    else:
        return None

# Hàm chuyển từ index về tên biến ban đầu


def decode_solution(solution, nurse_name_to_index):
    assignments = []
    index_to_nurse_name = {v: k for k, v in nurse_name_to_index.items()}
    day_mapping = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    for var in solution:
        parts = var.split("_")
        if parts[0] == 'x':
            nurse_id, day, shift, skill = parts[1], parts[2], parts[3], parts[4]
            nurse_name = index_to_nurse_name[int(nurse_id)]
            day_name = day_mapping[int(day)]
            assignments.append({
                "nurse": nurse_name,
                "day": day_name,
                "shift": shift,
                "skill": skill
            })
    return assignments

# Xuất file CNF


def export_cnf(filename="output.cnf", clauses=[]):
    with open(filename, "w") as f:
        f.write(f"p cnf {counter - 1} {len(clauses)}\n")
        for clause in clauses:
            f.write(f"{clause}\n")


# if __name__ == "__main__":
#     scenario, history, weekday, N, D, S, SK, W, nurse_skills, forbidden_shifts, shift_off_requests, nurse_name_to_index, nurse_contracts, contracts, nurse_history = load_data(
#         "Sc-n005w4.json", "H0-n005w4-1.json", "WD-n005w4-5.json")
#     hard_clauses = constraint_H1(
#         N, D, S, SK, nurse_skills) + constraint_H3(N, D, S, SK, nurse_skills, forbidden_shifts)
#     hard_clauses += constraint_H2(
#         N, D, S, SK, weekday, nurse_skills)
#     export_cnf(clauses=hard_clauses)

#     soft_clauses = []
#     # soft_clauses = constraint_S1(
#     #     N, D, S, SK, weekday, nurse_skills, penalty_weight=30) + constraint_S4_SOR(N, D, S, SK, nurse_skills,
#     #                                                                                shift_off_requests, nurse_name_to_index, penalty_weight=10) + constraint_S5(N, D, S, nurse_skills, nurse_contracts,
#                                                                                                                                                             #    contracts, penalty_weight=10)

#     solution = solve_maxsat(hard_clauses, soft_clauses)
#     # solution = solve_sat(all_clauses)
#     if solution:
#         assignments = decode_solution(solution)
#         for assign in assignments:
#             print(assign)
#     else:
#         print("Không tìm thấy lời giải khả thi.")


def save_solution(assignments, scenario_id, week_index, solution_file):
    solution = {
        "scenario": scenario_id,
        "week": week_index,
        "assignments": assignments
    }
    output_dir = "output"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    solution_file_path = os.path.join(output_dir, solution_file)
    with open(solution_file_path, 'w') as f:
        json.dump(solution, f, indent=4)


# python nurse_rostering_sat.py --sce input/Sc-n005w4.json --his input/H0-n005w4-1.json --week input/WD-n005w4-5.json --sol Sol-n005w4-5-0.json
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Nurse Rostering Problem Solver")
    parser.add_argument('--sce', required=True, help='Scenario File')
    parser.add_argument('--his', required=True, help='Initial History File')
    parser.add_argument('--week', required=True, help='Week Data File')
    parser.add_argument('--sol', required=True, help='Solution File Name')
    parser.add_argument('--cusIn', help='Custom Input File')
    parser.add_argument('--cusOut', help='Custom Output File')
    parser.add_argument('--rand', type=int, help='Random Seed')
    parser.add_argument('--timeout', type=int, help='Timeout in Seconds')

    args = parser.parse_args()

    if args.rand:
        random.seed(args.rand)

    scenario, history, weekday, N, D, S, SK, W, nurse_skills, forbidden_shifts, shift_off_requests, nurse_name_to_index, nurse_contracts, contracts, nurse_history = load_data(
        args.sce, args.his, args.week)

    hard_clauses = constraint_H1(N, D, S, SK, nurse_skills) + \
        constraint_H3(N, D, S, SK, nurse_skills, forbidden_shifts)
    hard_clauses += constraint_H2(N, D, S, SK, weekday, nurse_skills)
    export_cnf(clauses=hard_clauses)

    soft_clauses = []
    soft_clauses += constraint_S1(N, D, S, SK,
                                  weekday, nurse_skills, penalty_weight=30)
    soft_clauses += constraint_S4_SOR(N, D, S, SK, nurse_skills,
                                      shift_off_requests, nurse_name_to_index, penalty_weight=10)
    soft_clauses += constraint_S5(N, D, S, nurse_skills,
                                  nurse_contracts, contracts, penalty_weight=10)

    solution = solve_maxsat(hard_clauses, soft_clauses)
    if solution:
        assignments = decode_solution(solution, nurse_name_to_index)

        # Extract scenario ID from the scenario file
        scenario_id = scenario['id']
        week_index = 0  # Assuming we are solving the first week of the period

        # Generate solution file name
        solution_file = f"sol-week{week_index}.json"

        save_solution(assignments, scenario_id, week_index, solution_file)
        print(f"Solution saved in output/{solution_file}")
    else:
        print("No solutions.")
