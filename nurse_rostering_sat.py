# nurse_rostering_sat.py

from ortools.sat.python import cp_model
import time
import re
import os
import json
import argparse
import random
from itertools import combinations
from pypblib import pblib
from pypblib.pblib import PBConfig, Pb2cnf
from pysat.solvers import Glucose3
from pysat.formula import WCNF
from pysat.examples.rc2 import RC2, RC2Stratified
import concurrent.futures


variable_dict = {}
reverse_variable_dict = {}
counter = 1
max_var_cmin = 0


def get_variable(name):
    global counter
    if name not in variable_dict and counter not in reverse_variable_dict:
        variable_dict[name] = counter
        reverse_variable_dict[counter] = name
        counter += 1
    return variable_dict[name]


def load_data(scenario_file, history_file, weekday_file):
    with open(scenario_file) as f:
        scenario = json.load(f)
    with open(history_file) as f:
        history = json.load(f)
    with open(weekday_file) as f:
        weekday = json.load(f)

    N = len(scenario['nurses'])
    D = 7
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
    nurse_history = history['nurseHistory']

    # Map shift types by ID
    shift_types = {shift['id']: shift for shift in scenario['shiftTypes']}

    return scenario, history, weekday, N, D, S, SK, W, nurse_skills, forbidden_shifts, shift_off_requests, nurse_name_to_index, nurse_contracts, contracts, nurse_history, shift_types


def get_Cmin(weekday, d, s, sk):
    day_mapping = {0: 'Monday', 1: 'Tuesday', 2: 'Wednesday',
                   3: 'Thursday', 4: 'Friday', 5: 'Saturday', 6: 'Sunday'}
    day = day_mapping.get(d, 'Monday')

    for req in weekday.get('requirements', []):
        if req['shiftType'] == s and req['skill'] == sk:
            return req.get(f'requirementOn{day}', {}).get('minimum', 0)
    return 0


def get_Copt(weekday, d, s, sk):
    day_mapping = {0: 'Monday', 1: 'Tuesday', 2: 'Wednesday',
                   3: 'Thursday', 4: 'Friday', 5: 'Saturday', 6: 'Sunday'}
    day = day_mapping.get(d, 'Monday')

    for req in weekday.get('requirements', []):
        if req['shiftType'] == s and req['skill'] == sk:
            return req.get(f'requirementOn{day}', {}).get('optimal', 0)
    return 0


def constraint_H1(N, D, S, SK, nurse_skills):
    clauses = []
    for n in range(N):
        for d in range(D):
            shifts = [get_variable(f"x_{n}_{d}_{s}_{sk}")
                      for s in S for sk in nurse_skills.get(n, [])]

            e_var = get_variable(f"e_{n}_{d}")
            clauses.append(f"-{e_var} {' '.join(map(str, shifts))} 0")
            for shift in shifts:
                clauses.append(f"-{shift} {e_var} 0")

            # Create the "o" variable for each shift
            for s in S:
                o_var = get_variable(f"o_{n}_{d}_{s}")
                shift_vars = [get_variable(
                    f"x_{n}_{d}_{s}_{sk}") for sk in nurse_skills.get(n, [])]
                # If "o" is true, at least one of the shift variables must be true
                clauses.append(f"-{o_var} {' '.join(map(str, shift_vars))} 0")
                # If any shift variable is true, "o" must be true
                for shift_var in shift_vars:
                    clauses.append(f"-{shift_var} {o_var} 0")

            for (s1, s2) in combinations(shifts, 2):
                clauses.append(f"-{s1} -{s2} 0")
    return clauses

def constraint_H3(N, D, S, SK, nurse_skills, forbidden_shifts, nurse_history):
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

    # Apply constraints using last assigned shift type from history
    if nurse_history:
        for nurse in nurse_history:
            nurse_id = nurse_name_to_index[nurse['nurse']]
            last_shift_type = nurse['lastAssignedShiftType']
            if last_shift_type in [fs['precedingShiftType'] for fs in forbidden_shifts]:
                for forbidden_shift in forbidden_shifts:
                    if forbidden_shift['precedingShiftType'] == last_shift_type:
                        for s2 in forbidden_shift['succeedingShiftTypes']:
                            for sk in nurse_skills.get(nurse_id, []):
                                var2 = get_variable(
                                    f"x_{nurse_id}_0_{s2}_{sk}")
                                clauses.append(f"-{var2} 0")

    return clauses


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
    config = PBConfig()
    config.set_PB_Encoder(pblib.PB_BDD)
    pb2 = Pb2cnf(config)

    for d in range(D):
        for s in S:
            for sk in SK:
                Cmin = get_Cmin(weekday, d, s, sk)
                nurses = [get_variable(f"x_{n}_{d}_{s}_{sk}") for n in range(
                    N) if sk in nurse_skills.get(n, [])]

                # Ensure at least Cmin nurses are assigned (hard constraint)
                if Cmin > 0 and len(nurses) >= Cmin:
                    formula = []
                    global max_var_cmin

                    max_var_cmin = pb2.encode_at_least_k(
                        nurses, Cmin, formula, len(variable_dict) + 1)

                    for clause in formula:
                        hard_clauses.append(" ".join(map(str, clause)) + " 0")

                    # Update variable_dict with new variables created by pb2.encode_at_least_k
                    for var in range(len(variable_dict) + 1, max_var_cmin + 1):
                        variable_dict[f"aux_cmin{var}"] = var
                        reverse_variable_dict[var] = f"aux_cmin{var}"

                    global counter
                    counter = max_var_cmin + 1

    return hard_clauses


# S1. Optimal coverage
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
                if Copt > 0 and len(nurses) >= Copt:
                    formula = []
                    max_var_copt = pb2.encode_at_least_k(
                        nurses, Copt, formula, len(variable_dict) + 1)
                    for clause in formula:
                        soft_clauses.append(
                            (penalty_weight, " ".join(map(str, clause)) + " 0"))

                    for var in range(len(variable_dict) + 1, max_var_copt + 1):
                        variable_dict[f"aux_cmax{var}"] = var
                        reverse_variable_dict[var] = f"aux_cmax{var}"

                    global counter
                    counter = max_var_copt + 1
    # print(soft_clauses)
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


def constraint_S5(N, D, S, nurse_skills, nurse_contracts, contracts, penalty_weight=30):
    soft_clauses = []
    weekends = [(5, 6)]  # Saturday (5) and Sunday (6)

    for n in range(N):
        contract_id = nurse_contracts[n]
        contract = contracts[contract_id]

        if contract.get('completeWeekends', 0) == 1:
            d1, d2 = weekends[0]
            # Create variables for working on Saturday and Sunday
            w1 = get_variable(f"e_{n}_{d1}")
            w2 = get_variable(f"e_{n}_{d2}")
            # w1 = get_variable(f"w1_{n}")
            # w2 = get_variable(f"w2_{n}")

            # # p = 1 if the nurse works on any shift during the day
            # p_d1_vars = [get_variable(f"x_{n}_{d1}_{s}_{sk}")
            #              for s in S for sk in nurse_skills.get(n, [])]
            # p_d2_vars = [get_variable(f"x_{n}_{d2}_{s}_{sk}")
            #              for s in S for sk in nurse_skills.get(n, [])]

            # # Create clauses to ensure that if w1 is true, then at least one of p_d1_vars is true
            # soft_clauses.append(
            #     (penalty_weight, f"-{w1} {' '.join(map(str, p_d1_vars))} 0"))
            # for p_d1 in p_d1_vars:
            #     soft_clauses.append((penalty_weight, f"-{p_d1} {w1} 0"))

            # # Create clauses to ensure that if w2 is true, then at least one of p_d2_vars is true
            # soft_clauses.append(
            #     (penalty_weight, f"-{w2} {' '.join(map(str, p_d2_vars))} 0"))
            # for p_d2 in p_d2_vars:
            #     soft_clauses.append((penalty_weight, f"-{p_d2} {w2} 0"))

            # Add clauses to ensure the nurse works both days or none
            soft_clauses.append((penalty_weight, f"-{w1} {w2} 0"))
            soft_clauses.append((penalty_weight, f"{w1} -{w2} 0"))

    return soft_clauses



# SAT Solver (Glucose)
# def solve_maxsat(clauses):
    solver = Glucose3()
    for clause in clauses:
        solver.add_clause(
            list(map(int, clause.strip().split()[:-1])))  # Bỏ ký tự '0'

    if solver.solve():
        model = solver.get_model()
        print("Model found:", model)
        print("Reverse variable dict:", reverse_variable_dict)
        solution = [reverse_variable_dict[abs(var)] for var in model if var > 0 and abs(
            var) in reverse_variable_dict]
        print("Solution:", solution)
        return solution
    else:
        print("No solution found.")
        return []


# def old_constraint_S5(N, D, S, nurse_skills, nurse_contracts, contracts, penalty_weight=30):
    soft_clauses = []
    weekends = [(5, 6)]  # Saturday (5) and Sunday (6)

    for n in range(N):
        contract_id = nurse_contracts[n]
        contract = contracts[contract_id]

        if contract.get('completeWeekends', 0) == 1:
            d1, d2 = weekends[0]
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


def constraint_S2_cons_work_day(nurse_history, nurse_name_to_index, nurse_contracts, contracts, penalty_weight=30):
    soft_clauses = []

    for nurse in nurse_history:
        nurse_id = nurse_name_to_index[nurse['nurse']]
        cons_working_days = nurse.get('numberOfConsecutiveWorkingDays', 0)

        contract_id = nurse_contracts[nurse_id]
        contract = contracts[contract_id]
        CW_max = contract.get('maximumNumberOfConsecutiveWorkingDays', 0)
        CW_min = contract.get('minimumNumberOfConsecutiveWorkingDays', 0)

        # CW_max
        if cons_working_days == 0:
            for d in range(7 - CW_max):
                clause = []
                for j in range(CW_max + 1):
                    var = get_variable(f"e_{nurse_id}_{d + j}")
                    clause.append(f"-{var}")
                soft_clauses.append((penalty_weight, " ".join(clause) + " 0"))
        else:
            if cons_working_days >= CW_max:
                cons_working_days = CW_max

            for d in range(6, CW_max - 1, -1):
                clause = []
                for j in range(CW_max + 1):
                    var = get_variable(f"e_{nurse_id}_{d - j}")
                    clause.append(f"-{var}")
                soft_clauses.append((penalty_weight, " ".join(clause) + " 0"))

            for d in range(CW_max - 1, -1, -1):
                clause = []
                if abs(d - CW_max) > cons_working_days:
                    break
                for j in range(d + 1):
                    var = get_variable(f"e_{nurse_id}_{d - j}")
                    clause.append(f"-{var}")
                soft_clauses.append((penalty_weight, " ".join(clause) + " 0"))

        # CW_min
        for d in range(7 - CW_min + 1):
            clause = []
            today = get_variable(f"e_{nurse_id}_{d}")
            if d == 0:
                clause.append(f"-{today}")
            else:
                yesterday = get_variable(f"e_{nurse_id}_{d - 1}")
                clause.append(f"-{today} {yesterday}")
            for j in range(1, CW_min):
                next_day = get_variable(f"e_{nurse_id}_{d + j}")
                soft_clauses.append(
                    (penalty_weight, " ".join(clause) + f" {next_day} 0"))

        if cons_working_days != 0:
            if cons_working_days >= CW_min:
                continue
            else:
                needed_days = CW_min - cons_working_days
                for i in range(needed_days):
                    var = get_variable(f"e_{nurse_id}_{i}")
                    soft_clauses.append((penalty_weight, f"{var} 0"))

    return soft_clauses


def constraint_S2_cons_work_shift(nurse_history, nurse_name_to_index, shift_types, penalty_weight=15):
    soft_clauses = []

    for nurse in nurse_history:
        last_cons_working_shifts = nurse.get(
            'numberOfConsecutiveAssignments', 0)
        last_working_shift = nurse.get('lastAssignedShiftType', 0)
        nurse_id = nurse_name_to_index[nurse['nurse']]

        for shift_id, shift_info in shift_types.items():
            CS_max = shift_info.get('maximumNumberOfConsecutiveAssignments', 0)
            CS_min = shift_info.get('minimumNumberOfConsecutiveAssignments', 0)

            if shift_id != last_working_shift:
                cons_working_shifts = 0
            else:
                cons_working_shifts = last_cons_working_shifts

            # CS_max
            if cons_working_shifts == 0:
                for d in range(7 - CS_max):
                    clause = []
                    for j in range(CS_max + 1):
                        var = get_variable(
                            f"o_{nurse_id}_{d + j}_{shift_id}")
                        clause.append(f"-{var}")
                    soft_clauses.append(
                        (penalty_weight, " ".join(clause) + " 0"))
            else:
                if cons_working_shifts >= CS_max:
                    cons_working_shifts = CS_max

                for d in range(6, CS_max - 1, -1):
                    clause = []
                    for j in range(CS_max + 1):
                        var = get_variable(f"o_{nurse_id}_{d - j}_{shift_id}")
                        clause.append(f"-{var}")
                    soft_clauses.append(
                        (penalty_weight, " ".join(clause) + " 0"))

                for d in range(CS_max - 1, -1, -1):
                    clause = []
                    if abs(d - CS_max) > cons_working_shifts:
                        break
                    for j in range(d + 1):
                        var = get_variable(f"o_{nurse_id}_{d - j}_{shift_id}")
                        clause.append(f"-{var}")
                    soft_clauses.append(
                        (penalty_weight, " ".join(clause) + " 0"))

            # CS_min
            for d in range(7 - CS_min + 1):
                clause = []
                today = get_variable(f"o_{nurse_id}_{d}_{shift_id}")
                if d == 0:
                    clause.append(f"-{today}")
                else:
                    yesterday = get_variable(
                        f"o_{nurse_id}_{d - 1}_{shift_id}")
                    clause.append(f"-{today} {yesterday}")
                for j in range(1, CS_min):
                    next_day = get_variable(f"o_{nurse_id}_{d + j}_{shift_id}")
                    soft_clauses.append(
                        (penalty_weight, " ".join(clause) + f" {next_day} 0"))

            if cons_working_shifts != 0:
                if cons_working_shifts >= CS_min:
                    continue
                else:
                    needed_days = CS_min - cons_working_shifts
                    for i in range(needed_days):
                        var = get_variable(f"o_{nurse_id}_{i}_{shift_id}")
                        soft_clauses.append((penalty_weight, f"{var} 0"))

    return soft_clauses


def constraint_S3(nurse_history, nurse_name_to_index, nurse_contracts, contracts, penalty_weight=30):
    soft_clauses = []

    for nurse in nurse_history:
        nurse_id = nurse_name_to_index[nurse['nurse']]
        cons_working_days = nurse.get('numberOfConsecutiveDaysOff', 0)

        contract_id = nurse_contracts[nurse_id]
        contract = contracts[contract_id]
        CF_max = contract.get('maximumNumberOfConsecutiveDaysOff', 0)
        CF_min = contract.get('minimumNumberOfConsecutiveDaysOff', 0)

        # CF_max
        if cons_working_days == 0:
            for d in range(7 - CF_max):
                clause = []
                for j in range(CF_max + 1):
                    var = get_variable(f"e_{nurse_id}_{d + j}")
                    clause.append(f"{var}")
                soft_clauses.append((penalty_weight, " ".join(clause) + " 0"))
        else:
            if cons_working_days >= CF_max:
                cons_working_days = CF_max

            for d in range(6, CF_max - 1, -1):
                clause = []
                for j in range(CF_max + 1):
                    var = get_variable(f"e_{nurse_id}_{d - j}")
                    clause.append(f"{var}")
                soft_clauses.append((penalty_weight, " ".join(clause) + " 0"))

            for d in range(CF_max - 1, -1, -1):
                clause = []
                if abs(d - CF_max) > cons_working_days:
                    break
                for j in range(d + 1):
                    var = get_variable(f"e_{nurse_id}_{d - j}")
                    clause.append(f"{var}")
                soft_clauses.append((penalty_weight, " ".join(clause) + " 0"))

        # CF_min
        for d in range(7 - CF_min + 1):
            clause = []
            today = get_variable(f"e_{nurse_id}_{d}")
            if d == 0:
                clause.append(f"{today}")
            else:
                yesterday = get_variable(f"e_{nurse_id}_{d - 1}")
                clause.append(f"{today} -{yesterday}")
            for j in range(1, CF_min):
                next_day = get_variable(f"e_{nurse_id}_{d + j}")
                soft_clauses.append(
                    (penalty_weight, " ".join(clause) + f" -{next_day} 0"))

        if cons_working_days != 0:
            if cons_working_days >= CF_min:
                continue
            else:
                needed_days = CF_min - cons_working_days
                for i in range(needed_days):
                    var = get_variable(f"e_{nurse_id}_{i}")
                    soft_clauses.append((penalty_weight, f"-{var} 0"))

    return soft_clauses
# MaxSAT Solver (RC2)


def solve_maxsat_RC2_stratified(hard_clauses, soft_clauses, timeout=100000, solver_type='rc2stratified'):
    wcnf = WCNF()

    # Add hard constraints
    for clause in hard_clauses:
        wcnf.append([int(lit) for lit in clause.split() if lit != '0'])

    # Add soft constraints with penalty
    for weight, clause in soft_clauses:
        wcnf.append([int(lit)
                    for lit in clause.split() if lit != '0'], weight=weight)

    def solve():
        if solver_type == 'rc2stratified':
            solver = RC2Stratified(wcnf)
        elif solver_type == 'rc2':
            solver = RC2(wcnf)
        else:
            raise ValueError(f"Unknown solver type: {solver_type}")

        return solver.compute()

    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(solve)
        try:
            solution = future.result(timeout=timeout)  # Set timeout
            return [reverse_variable_dict[abs(var)] for var in solution if var > 0] if solution else None
        except concurrent.futures.TimeoutError:
            print("MaxSAT solving timed out!")
            return None


def solve_maxsat_RC2(hard_clauses, soft_clauses):
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
                "shiftType": shift,
                "skill": skill
            })
    return assignments


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


def extract_week_index(solution_file):
    match = re.search(r'week(\d+)', solution_file)
    if match:
        return int(match.group(1))
    else:
        return None


def save_solution(assignments, scenario_id, week_index, solution_file):
    solution = {
        "scenario": scenario_id,
        "week": week_index,
        "assignments": assignments
    }
    # output_dir = "output"
    # if not os.path.exists(output_dir):
    #     os.makedirs(output_dir)
    # solution_file_path = os.path.join(output_dir, solution_file)
    with open(solution_file, 'w') as f:
        json.dump(solution, f, indent=4)


def load_last_sunday_shifts(filename):
    if os.path.exists(filename):
        with open(filename, 'r') as f:
            return json.load(f)
    return []


# python nurse_rostering_sat.py `
# --sce input/n012w8/Sc-n012w8.json `
# --his input/n012w8/H0-n012w8-0.json `
# --week input/n012w8/WD-n012w8-3.json `
# --sol week0.json
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
    parser.add_argument('--timeout', type=float, help='Timeout in Seconds')

    args = parser.parse_args()

    if args.rand:
        random.seed(args.rand)

    scenario, history, weekday, N, D, S, SK, W, nurse_skills, forbidden_shifts, shift_off_requests, nurse_name_to_index, nurse_contracts, contracts, nurse_history, shift_types = load_data(
        args.sce, args.his, args.week)

    hard_clauses = []
    hard_clauses += constraint_H1(N, D, S, SK, nurse_skills)
    hard_clauses += constraint_H3(N, D, S, SK,
                                  nurse_skills, forbidden_shifts, nurse_history)
    hard_clauses += constraint_H2(N, D, S, SK, weekday, nurse_skills)
    # export_cnf(clauses=hard_clauses)

    soft_clauses = []
    soft_clauses += constraint_S1(N, D, S, SK,
                                  weekday, nurse_skills, penalty_weight=30)
    soft_clauses += constraint_S5(N, D, S, nurse_skills,
                                  nurse_contracts, contracts, penalty_weight=30)
    # # soft_clauses += old_constraint_S5(N, D, S, nurse_skills,nurse_contracts, contracts, penalty_weight=30)
    soft_clauses += constraint_S4_SOR(N, D, S, SK, nurse_skills,
                                      shift_off_requests, nurse_name_to_index, penalty_weight=10)
    soft_clauses += constraint_S2_cons_work_day(
        nurse_history, nurse_name_to_index, nurse_contracts, contracts, penalty_weight=30)
    soft_clauses += constraint_S2_cons_work_shift(
        nurse_history, nurse_name_to_index, shift_types, penalty_weight=15)
    soft_clauses += constraint_S3(nurse_history, nurse_name_to_index,
                                  nurse_contracts, contracts, penalty_weight=30)
    export_cnf(clauses=hard_clauses+soft_clauses)

    print(f"Number of hard clauses: {len(hard_clauses)}")
    print(f"Number of soft clauses: {len(soft_clauses)}")
    print(f"Total number of variables: {counter - 1}")

    start_time = time.time()
    # solution = solve_maxsat_RC2(hard_clauses, soft_clauses)
    solution = solve_maxsat_RC2_stratified(
        hard_clauses, soft_clauses, timeout=100000)
    solving_time = time.time() - start_time
    print(f"Solving time: {solving_time:.2f} seconds")
    if solution:
        assignments = decode_solution(solution, nurse_name_to_index)

        # Extract scenario ID from the scenario file
        scenario_id = scenario['id']
        # Assuming we are solving the first week of the period
        week_index = extract_week_index(args.sol)

        # Generate solution file name
        solution_file = args.sol

        save_solution(assignments, scenario_id, week_index, solution_file)

        print(f"Solution saved in {solution_file}")
    else:
        print("No solutions.")

# 4 weeks
# java -jar Simulator_withTimeout.jar `
# --his input\n005w4\H0-n005w4-0.json `
# --sce input\n005w4\Sc-n005w4.json `
# --weeks input\n005w4\WD-n005w4-1.json input\n005w4\WD-n005w4-2.json input\n005w4\WD-n005w4-3.json input\n005w4\WD-n005w4-3.json `
# --solver "python nurse_rostering_sat.py" `
# --runDir SC_Encoding/ `
# --outDir "D:\UET_Materials\UET_6th_Semester(23-24)\NCKH\Nurse Rostering Prob\NRP Solver\Simulator_withTimeout\Simulator_out" `
# --cus `
# --timeout 4

# 4 weeks
# java -jar Simulator_withTimeout.jar `
# --his input\n005w4\H0-n005w4-1.json `
# --sce input\n005w4\Sc-n005w4.json `
# --weeks input\n005w4\WD-n005w4-5.json input\n005w4\WD-n005w4-3.json input\n005w4\WD-n005w4-1.json input\n005w4\WD-n005w4-0.json `
# --solver "python nurse_rostering_sat.py" `
# --runDir SC_Encoding/ `
# --outDir "D:\UET_Materials\UET_6th_Semester(23-24)\NCKH\Nurse Rostering Prob\NRP Solver\Simulator_withTimeout\Simulator_out" `
# --cus `
# --timeout 4


# 4 weeks
# java -jar Simulator_withTimeout.jar `
# --his input\n005w4\H0-n005w4-2.json `
# --sce input\n005w4\Sc-n005w4.json `
# --weeks input\n005w4\WD-n005w4-6.json input\n005w4\WD-n005w4-7.json input\n005w4\WD-n005w4-8.json input\n005w4\WD-n005w4-9.json `
# --solver "python nurse_rostering_sat.py" `
# --runDir SC_Encoding/ `
# --outDir "D:\UET_Materials\UET_6th_Semester(23-24)\NCKH\Nurse Rostering Prob\NRP Solver\Simulator_withTimeout\Simulator_out" `
# --cus `
# --timeout 4


# n21ww4
# 4 weeks
# java -jar Simulator_withTimeout.jar `
# --his input\n021w4\H0-n021w4-0.json `
# --sce input\n021w4\Sc-n021w4.json `
# --weeks input\n021w4\WD-n021w4-5.json input\n021w4\WD-n021w4-4.json input\n021w4\WD-n021w4-1.json input\n021w4\WD-n021w4-2.json `
# --solver "python nurse_rostering_sat.py" `
# --runDir SC_Encoding/ `
# --outDir "D:\UET_Materials\UET_6th_Semester(23-24)\NCKH\Nurse Rostering Prob\NRP Solver\Simulator_withTimeout\Simulator_out" `
# --cus

# 4 weeks
# java -jar Simulator_withTimeout.jar `
# --his input\n021w4\H0-n021w4-1.json `
# --sce input\n021w4\Sc-n021w4.json `
# --weeks input\n021w4\WD-n021w4-0.json input\n021w4\WD-n021w4-6.json input\n021w4\WD-n021w4-1.json input\n021w4\WD-n021w4-6.json `
# --solver "python nurse_rostering_sat.py" `
# --runDir SC_Encoding/ `
# --outDir "D:\UET_Materials\UET_6th_Semester(23-24)\NCKH\Nurse Rostering Prob\NRP Solver\Simulator_withTimeout\Simulator_out" `
# --cus

# 4 weeks
# java -jar Simulator_withTimeout.jar `
# --his input\n021w4\H0-n021w4-2.json `
# --sce input\n021w4\Sc-n021w4.json `
# --weeks input\n021w4\WD-n021w4-8.json input\n021w4\WD-n021w4-1.json input\n021w4\WD-n021w4-4.json input\n021w4\WD-n021w4-3.json `
# --solver "python nurse_rostering_sat.py" `
# --runDir SC_Encoding/ `
# --outDir "D:\UET_Materials\UET_6th_Semester(23-24)\NCKH\Nurse Rostering Prob\NRP Solver\Simulator_withTimeout\Simulator_out" `
# --cus

# n12w8
# 8 weeks
# java -jar Simulator_withTimeout.jar `
# --his input\n012w8\H0-n012w8-0.json `
# --sce input\n012w8\Sc-n012w8.json `
# --weeks input\n012w8\WD-n012w8-3.json input\n012w8\WD-n012w8-5.json input\n012w8\WD-n012w8-0.json input\n012w8\WD-n012w8-2.json input\n012w8\WD-n012w8-0.json input\n012w8\WD-n012w8-4.json input\n012w8\WD-n012w8-5.json input\n012w8\WD-n012w8-2.json `
# --solver "python nurse_rostering_sat.py" `
# --runDir SC_Encoding/ `
# --outDir "D:\UET_Materials\UET_6th_Semester(23-24)\NCKH\Nurse Rostering Prob\NRP Solver\Simulator_withTimeout\Simulator_out" `
# --cus `
# --timeout 30

# 8 weeks
# java -jar Simulator_withTimeout.jar `
# --his input\n012w8\H0-n012w8-1.json `
# --sce input\n012w8\Sc-n012w8.json `
# --weeks input\n012w8\WD-n012w8-7.json input\n012w8\WD-n012w8-7.json input\n012w8\WD-n012w8-0.json input\n012w8\WD-n012w8-8.json input\n012w8\WD-n012w8-9.json input\n012w8\WD-n012w8-3.json input\n012w8\WD-n012w8-2.json input\n012w8\WD-n012w8-6.json `
# --solver "python nurse_rostering_sat.py" `
# --runDir SC_Encoding/ `
# --outDir "D:\UET_Materials\UET_6th_Semester(23-24)\NCKH\Nurse Rostering Prob\NRP Solver\Simulator_withTimeout\Simulator_out" `
# --cus `
# --timeout 30

# 8 weeks
# java -jar Simulator_withTimeout.jar `
# --his input\n012w8\H0-n012w8-2.json `
# --sce input\n012w8\Sc-n012w8.json `
# --weeks input\n012w8\WD-n012w8-4.json input\n012w8\WD-n012w8-5.json input\n012w8\WD-n012w8-6.json input\n012w8\WD-n012w8-7.json input\n012w8\WD-n012w8-2.json input\n012w8\WD-n012w8-1.json input\n012w8\WD-n012w8-2.json input\n012w8\WD-n012w8-1.json `
# --solver "python nurse_rostering_sat.py" `
# --runDir SC_Encoding/ `
# --outDir "D:\UET_Materials\UET_6th_Semester(23-24)\NCKH\Nurse Rostering Prob\NRP Solver\Simulator_withTimeout\Simulator_out" `
# --cus `
# --timeout 30


# n030w4_1_6-7-5-3
# java -jar Simulator_withTimeout.jar `
# --his input\n030w4\H0-n030w4-1.json `
# --sce input\n030w4\Sc-n030w4.json `
# --weeks input\n030w4\WD-n030w4-6.json input\n030w4\WD-n030w4-7.json input\n030w4\WD-n030w4-5.json input\n030w4\WD-n030w4-3.json `
# --solver "python nurse_rostering_sat.py" `
# --runDir SC_Encoding/ `
# --outDir "D:\UET_Materials\UET_6th_Semester(23-24)\NCKH\Nurse Rostering Prob\NRP Solver\Simulator_withTimeout\Simulator_out" `
# --cus

# n030w4_1_6-2-9-1
# java -jar Simulator_withTimeout.jar `
# --his input\n030w4\H0-n030w4-1.json `
# --sce input\n030w4\Sc-n030w4.json `
# --weeks input\n030w4\WD-n030w4-6.json input\n030w4\WD-n030w4-2.json input\n030w4\WD-n030w4-9.json input\n030w4\WD-n030w4-1.json `
# --solver "python nurse_rostering_sat.py" `
# --runDir SC_Encoding/ `
# --outDir "D:\UET_Materials\UET_6th_Semester(23-24)\NCKH\Nurse Rostering Prob\NRP Solver\Simulator_withTimeout\Simulator_out" `
# --cus

# n120w8
# 8 weeks
# java -jar Simulator_withTimeout.jar `
# --his input\n120w8\H0-n120w8-0.json `
# --sce input\n120w8\Sc-n120w8.json `
# --weeks input\n120w8\WD-n120w8-0.json input\n120w8\WD-n120w8-9.json input\n120w8\WD-n120w8-9.json input\n120w8\WD-n120w8-4.json input\n120w8\WD-n120w8-5.json input\n120w8\WD-n120w8-1.json input\n120w8\WD-n120w8-0.json input\n120w8\WD-n120w8-3.json `
# --solver "python nurse_rostering_sat.py" `
# --runDir SC_Encoding/ `
# --outDir "D:\UET_Materials\UET_6th_Semester(23-24)\NCKH\Nurse Rostering Prob\NRP Solver\Simulator_withTimeout\Simulator_out" `
# --cus `
# --timeout 30

# 8 weeks
# java -jar Simulator_withTimeout.jar `
# --his input\n120w8\H0-n120w8-1.json `
# --sce input\n120w8\Sc-n120w8.json `
# --weeks input\n120w8\WD-n120w8-7.json input\n120w8\WD-n120w8-2.json input\n120w8\WD-n120w8-6.json input\n120w8\WD-n120w8-4.json input\n120w8\WD-n120w8-5.json input\n120w8\WD-n120w8-2.json input\n120w8\WD-n120w8-0.json input\n120w8\WD-n120w8-2.json `
# --solver "python nurse_rostering_sat.py" `
# --runDir SC_Encoding/ `
# --outDir "D:\UET_Materials\UET_6th_Semester(23-24)\NCKH\Nurse Rostering Prob\NRP Solver\Simulator_withTimeout\Simulator_out" `
# --cus `
# --timeout 30
