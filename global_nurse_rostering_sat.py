from itertools import permutations
import subprocess
import os
from math import ceil
import json
import argparse
from itertools import combinations
from pypblib import pblib
from pypblib.pblib import PBConfig, Pb2cnf
from optilog.encoders.pb import Encoder

variable_dict = {}
reverse_variable_dict = {}
counter = 1
hard_clauses = []

pypblib_encoding = pblib.PB_BEST
optilog_encoding = 'best'


def get_variable(name):
    global counter, reverse_variable_dict
    if name not in variable_dict and counter not in reverse_variable_dict:
        if name.startswith('auxvarsc_'):
            parts = name.split('_')
            first, last = parts[1], parts[2]
            if first == last:
                return first

        variable_dict[name] = counter
        reverse_variable_dict[counter] = name
        counter += 1

    return variable_dict[name]


def map_to_x_variables():
    global hard_clauses
    for name in variable_dict:
        if name.startswith('e_'):
            parts = name.split('_')
            n, d = parts[1], parts[2]
            shifts = [get_variable(f"x_{n}_{d}_{s}_{sk}")
                      for s in S for sk in nurse_skills.get(int(n), [])]
            hard_clauses.append(
                f"-{variable_dict[name]} {' '.join(map(str, shifts))} 0")
            for shift in shifts:
                hard_clauses.append(f"-{shift} {variable_dict[name]} 0")

            # shift_vars = [get_variable(f"o_{n}_{d}_{s}") for s in S]
            # hard_clauses.append(
            #     f"-{variable_dict[name]} {' '.join(map(str, shift_vars))} 0"
            # )
            # for shift_var in shift_vars:
            #     hard_clauses.append(f"-{shift_var} {variable_dict[name]} 0")
        elif name.startswith('o_'):
            parts = name.split('_')
            n, d, s = parts[1], parts[2], parts[3]
            shift_vars = [get_variable(f"x_{n}_{d}_{s}_{sk}")
                          for sk in nurse_skills.get(int(n), [])]
            hard_clauses.append(
                f"-{variable_dict[name]} {' '.join(map(str, shift_vars))} 0")
            for shift_var in shift_vars:
                hard_clauses.append(f"-{shift_var} {variable_dict[name]} 0")
        elif name.startswith('q_'):
            parts = name.split('_')
            n, w = parts[1], parts[2]
            saturday = get_variable(f"e_{n}_{int(w) * 7 + 5}")
            sunday = get_variable(f"e_{n}_{int(w) * 7 + 6}")
            hard_clauses.append(
                f"-{variable_dict[name]} {saturday} {sunday} 0")
            hard_clauses.append(f"-{saturday} {variable_dict[name]} 0")
            hard_clauses.append(f"-{sunday} {variable_dict[name]} 0")


def load_data(scenario_file, history_file, week_files):
    with open(scenario_file) as f:
        scenario = json.load(f)
    with open(history_file) as f:
        history = json.load(f)

    weekdays = []
    for week_file in week_files:
        with open(week_file) as f:
            weekdays.append(json.load(f))

    N = len(scenario['nurses'])
    D = len(weekdays) * 7
    S = [shift['id'] for shift in scenario['shiftTypes']]
    SK = scenario['skills']
    W = scenario['numberOfWeeks']
    nurse_skills = {n: nurse['skills']
                    for n, nurse in enumerate(scenario['nurses'])}
    forbidden_shifts = scenario['forbiddenShiftTypeSuccessions']

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

    return scenario, history, weekdays, N, D, S, SK, W, nurse_skills, forbidden_shifts, nurse_name_to_index, nurse_contracts, contracts, nurse_history, shift_types


def get_week_index(day_index):
    return (day_index // 7)


def get_Cmin(weekdays, d, s, sk):
    week_index = get_week_index(d)
    weekday = weekdays[week_index]

    day_mapping = {0: 'Monday', 1: 'Tuesday', 2: 'Wednesday',
                   3: 'Thursday', 4: 'Friday', 5: 'Saturday', 6: 'Sunday'}
    day = day_mapping.get(d % 7, 'Monday')

    for req in weekday.get('requirements', []):
        if req['shiftType'] == s and req['skill'] == sk:
            return req.get(f'requirementOn{day}', {}).get('minimum', 0)
    return 0


def get_Copt(weekdays, d, s, sk):
    week_index = get_week_index(d)
    weekday = weekdays[week_index]

    day_mapping = {0: 'Monday', 1: 'Tuesday', 2: 'Wednesday',
                   3: 'Thursday', 4: 'Friday', 5: 'Saturday', 6: 'Sunday'}
    day = day_mapping.get(d % 7, 'Monday')

    for req in weekday.get('requirements', []):
        if req['shiftType'] == s and req['skill'] == sk:
            return req.get(f'requirementOn{day}', {}).get('optimal', 0)
    return 0


def constraint_aux(N, D, S, nurse_skills):
    clauses = []
    for n in range(N):
        for d in range(D):
            skills = [sk for sk in nurse_skills.get(n, [])]
            if len(skills) < 2:
                continue
            for s in S:
                shifts = [get_variable(f"x_{n}_{d}_{s}_{sk}")
                          for sk in nurse_skills.get(n, [])]
                for (s1, s2) in combinations(shifts, 2):
                    clauses.append(f"-{s1} -{s2} 0")
    return clauses


def constraint_H1(N, D, S):
    clauses = []
    for n in range(N):
        for d in range(D):
            shifts = [get_variable(f"o_{n}_{d}_{s}")
                      for s in S]

            for (s1, s2) in combinations(shifts, 2):
                clauses.append(f"-{s1} -{s2} 0")
    return clauses


def constraint_H3(N, D, forbidden_shifts, nurse_history):
    clauses = []
    for n in range(N):
        for d in range(D - 1):
            for forbidden_shift in forbidden_shifts:
                s1 = forbidden_shift['precedingShiftType']
                for s2 in forbidden_shift['succeedingShiftTypes']:
                    var1 = get_variable(f"o_{n}_{d}_{s1}")
                    var2 = get_variable(f"o_{n}_{d+1}_{s2}")
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
                            var2 = get_variable(f"o_{nurse_id}_0_{s2}")
                            hard_clauses.append(f"-{var2} 0")

    return clauses


def constraint_H3_SC(N, D, S, forbidden_shifts, nurse_history, weekdays):
    def encode_window(window, width, very_first_shift, n):
        # First window
        if window == 0:
            lastVar = window * width + width + very_first_shift - 1

            for i in range(width - 1, 0, -1):
                var = window * width + i + very_first_shift - 1
                var_R = get_variable(f'auxvarsc_{var}_{lastVar}')
                hard_clauses.append(f"-{var} {var_R} 0")

            for i in range(width, 1, -1):
                var = window * width + i + very_first_shift - 1
                var_R_1 = get_variable(f'auxvarsc_{var}_{lastVar}')
                var_R_2 = get_variable(f'auxvarsc_{var - 1}_{lastVar}')
                hard_clauses.append(f"-{var_R_1} {var_R_2} 0")

            for i in range(1, width, 1):
                var = window * width + i + very_first_shift - 1
                main = get_variable(f'auxvarsc_{var}_{lastVar}')
                sub = get_variable(f'auxvarsc_{var + 1}_{lastVar}')
                hard_clauses.append(f"{var} {sub} -{main} 0")

            for i in range(1, width, 1):
                var = window * width + i + very_first_shift - 1
                var_R = get_variable(f'auxvarsc_{var + 1}_{lastVar}')
                hard_clauses.append(f"-{var} -{var_R} 0")
        # Last window
        elif window == ceil(float(n) / width) - 1:
            if window == 3:
                print("check")
            firstVar = window * width + 1 + very_first_shift - 1

            for i in range(2, width + 1, 1):
                reverse_var = window * width + i + very_first_shift - 1
                var_R = get_variable(f'auxvarsc_{firstVar}_{reverse_var}')
                hard_clauses.append(f"-{reverse_var} {var_R} 0")

            for i in range(width - 1, 0, -1):
                reverse_var = window * width + width - i + very_first_shift - 1
                var_R_1 = get_variable(f'auxvarsc_{firstVar}_{reverse_var}')
                var_R_2 = get_variable(
                    f'auxvarsc_{firstVar}_{reverse_var + 1}')
                hard_clauses.append(f"-{var_R_1} {var_R_2} 0")

            for i in range(0, width - 1, 1):
                var = window * width + width - i + very_first_shift - 1
                main = get_variable(f'auxvarsc_{firstVar}_{var}')
                sub = get_variable(f'auxvarsc_{firstVar}_{var - 1}')
                hard_clauses.append(f"{sub} {var} -{main} 0")

            for i in range(width, 1, -1):
                reverse_var = window * width + i + very_first_shift - 1
                var_R = get_variable(f'auxvarsc_{firstVar}_{reverse_var - 1}')
                hard_clauses.append(f"-{reverse_var} -{var_R} 0")
        else:
            # Middle windows
            # Upper part
            firstVar = window * width + 1 + very_first_shift - 1

            for i in range(2, width + 1, 1):
                reverse_var = window * width + i + very_first_shift - 1
                var_R = get_variable(f'auxvarsc_{firstVar}_{reverse_var}')
                hard_clauses.append(f"-{reverse_var} {var_R} 0")

            for i in range(width - 1, 0, -1):
                reverse_var = window * width + width - i + very_first_shift - 1
                var_R_1 = get_variable(f'auxvarsc_{firstVar}_{reverse_var}')
                var_R_2 = get_variable(
                    f'auxvarsc_{firstVar}_{reverse_var + 1}')
                hard_clauses.append(f"-{var_R_1} {var_R_2} 0")

            for i in range(0, width - 1, 1):
                var = window * width + width - i + very_first_shift - 1
                main = get_variable(f'auxvarsc_{firstVar}_{var}')
                sub = get_variable(f'auxvarsc_{firstVar}_{var - 1}')
                hard_clauses.append(f"{sub} {var} -{main} 0")

            for i in range(width, 1, -1):
                reverse_var = window * width + i + very_first_shift - 1
                var_R = get_variable(f'auxvarsc_{firstVar}_{reverse_var - 1}')
                hard_clauses.append(f"-{reverse_var} -{var_R} 0")

            # Lower part
            lastVar = window * width + width + very_first_shift - 1

            for i in range(width - 1, 0, -1):
                var = window * width + i + very_first_shift - 1
                var_R = get_variable(f'auxvarsc_{var}_{lastVar}')
                hard_clauses.append(f"-{var} {var_R} 0")

            for i in range(width, 1, -1):
                var = window * width + i + very_first_shift - 1
                var_R_1 = get_variable(f'auxvarsc_{var}_{lastVar}')
                var_R_2 = get_variable(f'auxvarsc_{var - 1}_{lastVar}')
                hard_clauses.append(f"-{var_R_1} {var_R_2} 0")

            for i in range(1, width, 1):
                var = window * width + i + very_first_shift - 1
                main = get_variable(f'auxvarsc_{var}_{lastVar}')
                sub = get_variable(f'auxvarsc_{var + 1}_{lastVar}')
                hard_clauses.append(f"{var} {sub} -{main} 0")

    def glue_window(window, isLack, very_first_shift):
        for i in range(1, width, 1):
            if isLack:
                if width == 8 and (i == 1 or i == 2 or i == 3 or i == 5 or i == 7):
                    continue
                if width == 4 and i == 1:
                    continue
            first_reverse_var = (window + 1) * width + 1 + very_first_shift - 1
            last_var = window * width + width + very_first_shift - 1
            reverse_var = (window + 1) * width + i + very_first_shift - 1
            var = window * width + i + 1 + very_first_shift - 1

            var_R_1 = get_variable(f'auxvarsc_{var}_{last_var}')
            var_R_2 = get_variable(
                f'auxvarsc_{first_reverse_var}_{reverse_var}')

            hard_clauses.append(f"-{var_R_1} -{var_R_2} 0")

    hard_clauses = []
    width = len(S)
    # isLack = False
    isLack = True

    for n in range(N):
        shifts = [get_variable(f"o_{n}_{d}_{s}")
                  for d in range(D) for s in S]
        very_first_shift = shifts[0]

        for gw in range(0, len(weekdays) * 7):
            encode_window(gw, width, very_first_shift,
                          width * len(weekdays) * 7)

        for gw in range(0, len(weekdays) * 7 - 1):
            glue_window(gw, isLack, very_first_shift)

    if nurse_history:
        for nurse in nurse_history:
            nurse_id = nurse_name_to_index[nurse['nurse']]
            last_shift_type = nurse['lastAssignedShiftType']
            if last_shift_type in [fs['precedingShiftType'] for fs in forbidden_shifts]:
                for forbidden_shift in forbidden_shifts:
                    if forbidden_shift['precedingShiftType'] == last_shift_type:
                        for s2 in forbidden_shift['succeedingShiftTypes']:
                            #     for sk in nurse_skills.get(nurse_id, []):
                            #         var2 = get_variable(
                            #             f"x_{nurse_id}_0_{s2}_{sk}")
                            #         hard_clauses.append(f"-{var2} 0")
                            var2 = get_variable(
                                f"o_{nurse_id}_0_{s2}")
                            hard_clauses.append(f"-{var2} 0")
    return hard_clauses


def constraint_optilog_H2(N, D, S, SK, weekdays, nurse_skills):
    clauses = []

    for d in range(D):
        for s in S:
            for sk in SK:
                Cmin = get_Cmin(weekdays, d, s, sk)
                Copt = get_Copt(weekdays, d, s, sk)
                nurses = [get_variable(f"x_{n}_{d}_{s}_{sk}") for n in range(
                    N) if sk in nurse_skills.get(n, [])]

                # Ensure at least Cmin nurses are assigned (hard constraint)
                if Cmin > 0 and len(nurses) >= Cmin:

                    max_var_cmin, formula = Encoder.at_least_k(
                        nurses, Cmin, max_var=len(variable_dict), encoding=optilog_encoding)
                    for clause in formula:
                        clauses.append(" ".join(map(str, clause)) + " 0")

                    # Update variable_dict with new variables created by pb2.encode_at_least_k
                    for var in range(len(variable_dict) + 1, max_var_cmin + 1):
                        variable_dict[f"aux_cmin{var}"] = var
                        reverse_variable_dict[var] = f"aux_cmin{var}"

                    global counter
                    counter = max_var_cmin + 1

    return clauses


def constraint_new_optilog_H2(N, D, S, SK, weekdays, nurse_skills):
    clauses = []

    for d in range(D):
        for s in S:
            for sk in SK:
                Cmin = get_Cmin(weekdays, d, s, sk)
                Copt = get_Copt(weekdays, d, s, sk)
                nurses = [get_variable(f"x_{n}_{d}_{s}_{sk}") for n in range(
                    N) if sk in nurse_skills.get(n, [])]

                # Ensure at least Cmin nurses are assigned (hard constraint)
                if Cmin > 0 and len(nurses) >= Cmin and Cmin == Copt:

                    max_var_cmin, formula = Encoder.at_least_k(
                        nurses, Cmin, max_var=len(variable_dict), encoding=optilog_encoding)
                    for clause in formula:
                        clauses.append(" ".join(map(str, clause)) + " 0")

                    # Update variable_dict with new variables created by pb2.encode_at_least_k
                    for var in range(len(variable_dict) + 1, max_var_cmin + 1):
                        variable_dict[f"aux_cmin{var}"] = var
                        reverse_variable_dict[var] = f"aux_cmin{var}"

                    global counter
                    counter = max_var_cmin + 1

    return clauses
# S1. Optimal coverage


def constraint_S1_pypblib(N, D, S, SK, weekdays, nurse_skills, penalty_weight):
    """
    Tạo các ràng buộc mềm S1 (phạt thiếu hụt so với Copt) sử dụng pypblib
    để mã hóa phần ràng buộc cứng liên quan đến biến phạt.

    Thêm các mệnh đề CỨNG cần thiết vào danh sách global `hard_clauses`.
    Trả về danh sách các mệnh đề MỀM.
    """
    global counter, hard_clauses, variable_dict, reverse_variable_dict  # Khai báo để cập nhật biến toàn cục

    soft_clauses_for_S1 = []  # Danh sách cục bộ cho mệnh đề mềm

    # Khởi tạo cấu hình và bộ mã hóa pypblib
    config = PBConfig()
    # Bạn có thể chọn encoder khác nếu muốn, ví dụ PB_BDD, PB_SORTINGNETWORKS
    # PB_BEST thường tự chọn encoder tốt
    config.set_PB_Encoder(pypblib_encoding)
    pb2 = Pb2cnf(config)

    for d in range(D):
        for s in S:
            for sk in SK:
                Copt = get_Copt(weekdays, d, s, sk)
                Cmin = get_Cmin(weekdays, d, s, sk)

                # Chỉ phạt khi Copt > Cmin (vì H2 đã đảm bảo >= Cmin)
                if Copt <= Cmin:
                    continue

                # Lấy danh sách biến y tá có thể làm ca này
                nurses = [get_variable(f"x_{n}_{d}_{s}_{sk}")
                          for n in range(N) if sk in nurse_skills.get(n, [])]

                # Số lượng thiếu hụt tối đa có thể xảy ra so với Copt (đã đảm bảo >= Cmin)
                # Nếu không có y tá nào, thiếu tối đa Copt - Cmin (nếu Copt > Cmin)
                max_shortfall = Copt - Cmin

                if max_shortfall <= 0:
                    continue

                # Tạo các biến phạt cho sự thiếu hụt
                penalty_vars = []
                for j in range(max_shortfall):
                    # get_variable sẽ tự tăng counter và cập nhật dicts
                    # Đặt tên rõ ràng hơn cho biến phạt liên quan đến pypblib
                    p_var = get_variable(f"penalty_s1_pblib_{d}_{s}_{sk}_{j}")
                    penalty_vars.append(p_var)

                # --- RÀNG BUỘC CỨNG: sum(nurses) + sum(penalty_vars) >= Copt ---
                # Đây là phần chúng ta sẽ dùng pypblib để mã hóa
                combined_vars = nurses + penalty_vars

                # Trường hợp không có biến nào nhưng Copt > Cmin (không thể thỏa mãn)
                if not combined_vars and Copt > Cmin:
                    print(
                        f"CẢNH BÁO (S1 pypblib): Không thể đáp ứng Copt={Copt} cho d={d}, s={s}, sk={sk} vì không có y tá/biến phạt."
                    )
                    # Thêm ràng buộc cứng không thể thỏa mãn
                    # Đảm bảo biến 1 tồn tại
                    if 'dummy_unsat' not in variable_dict:
                        # Gọi để thêm vào dict nếu cần
                        get_variable('dummy_unsat')
                    hard_clauses.append("1 0")
                    hard_clauses.append("-1 0")
                    continue  # Bỏ qua lần lặp này

                elif combined_vars:
                    formula_hard = []
                    # Lấy ID biến lớn nhất hiện tại TRƯỚC khi gọi encode
                    current_top_var = counter - 1

                    # Mã hóa ràng buộc cứng Sum(combined_vars) >= Copt bằng pypblib
                    # ID biến phụ trợ sẽ bắt đầu từ current_top_var + 1
                    top_var_pblib = pb2.encode_at_least_k(
                        combined_vars, Copt, formula_hard, current_top_var + 1
                    )

                    # Thêm các mệnh đề CNF được tạo ra vào danh sách hard_clauses TOÀN CỤC
                    for clause in formula_hard:
                        hard_clauses.append(" ".join(map(str, clause)) + " 0")

                    # Cập nhật counter và dictionaries cho các biến phụ trợ MỚI
                    # mà pypblib đã tạo ra (từ current_top_var + 1 đến top_var_pblib)
                    for var_idx in range(current_top_var + 1, top_var_pblib + 1):
                        # Tạo tên duy nhất cho biến phụ trợ của pypblib
                        aux_pblib_name = f"aux_s1_pblib_{d}_{s}_{sk}_{var_idx}"
                        if var_idx not in reverse_variable_dict:
                            variable_dict[aux_pblib_name] = var_idx
                            reverse_variable_dict[var_idx] = aux_pblib_name
                        # else: # Nếu biến đã tồn tại, có thể có lỗi logic
                        #    print(f"Cảnh báo: Biến phụ trợ pypblib {var_idx} đã tồn tại.")

                    # Cập nhật counter toàn cục lên giá trị cao nhất mới được sử dụng
                    # Đảm bảo counter luôn là ID tiếp theo chưa được dùng
                    counter = max(counter, top_var_pblib + 1)

                # --- RÀNG BUỘC MỀM: Phạt việc sử dụng các biến phạt ---
                # Thêm vào danh sách soft_clauses_for_S1 CỤC BỘ của hàm này
                for p_var in penalty_vars:
                    soft_clauses_for_S1.append((penalty_weight, f"-{p_var} 0"))

    # Trả về danh sách các mệnh đề mềm ĐÃ được tạo bởi logic S1 này
    return soft_clauses_for_S1


def constraint_S1(N, D, S, SK, weekdays, nurse_skills, penalty_weight):
    global counter, variable_dict, reverse_variable_dict

    soft_clauses = []
    config = PBConfig()
    config.set_PB_Encoder(pypblib_encoding)
    # config.set_AMK_Encoder(pypblib_encoding)
    pb2 = Pb2cnf(config)

    for d in range(D):
        for s in S:
            for sk in SK:
                Copt = get_Copt(weekdays, d, s, sk)
                Cmin = get_Cmin(weekdays, d, s, sk)
                if Copt - Cmin <= 0:
                    continue

                # Penalize each missing nurse below Copt (soft constraint)
                if Copt > 0:
                    nurses = [get_variable(f"x_{n}_{d}_{s}_{sk}") for n in range(
                        N) if sk in nurse_skills.get(n, [])]
                    formula = []
                    max_var_copt = pb2.encode_at_least_k(
                        nurses, Copt, formula, len(variable_dict) + 1)
                    for clause in formula:
                        soft_clauses.append(
                            (penalty_weight, " ".join(map(str, clause)) + " 0"))

                    for var in range(len(variable_dict) + 1, max_var_copt + 1):
                        variable_dict[f"aux_cmax{var}"] = var
                        reverse_variable_dict[var] = f"aux_cmax{var}"

                    counter = max_var_copt + 1
    return soft_clauses


def constraint_S1_new_optilog(N, D, S, SK, weekdays, nurse_skills, penalty_weight):
    """
    Tạo các ràng buộc mềm để phạt việc không đáp ứng Copt, sử dụng biến phạt phụ trợ.
    Đồng thời thêm các ràng buộc cứng cần thiết vào danh sách hard_clauses toàn cục.
    """
    global counter, hard_clauses, variable_dict, reverse_variable_dict  # Khai báo các biến toàn cục sẽ sửa đổi

    soft_clauses_for_S1 = []  # Danh sách cục bộ cho các mệnh đề mềm mà hàm này trả về

    for d in range(D):
        for s in S:
            for sk in SK:
                Copt = get_Copt(weekdays, d, s, sk)
                Cmin = get_Cmin(weekdays, d, s, sk)

                # Chỉ phạt khi Copt lớn hơn Cmin một cách rõ ràng
                # Nếu Copt <= Cmin, ràng buộc cứng H2 đã đảm bảo không cần phạt
                if Copt <= Cmin:
                    continue

                # Lấy danh sách các biến y tá có thể làm ca này
                nurses = [get_variable(f"x_{n}_{d}_{s}_{sk}")
                          for n in range(N) if sk in nurse_skills.get(n, [])]

                # Tính số lượng thiếu hụt tối đa có thể xảy ra so với Copt,
                # giả sử Cmin đã được đáp ứng (do H2 là ràng buộc cứng)
                # Nếu không có y tá nào, shortfall có thể lên tới Copt
                # Nếu có y tá, shortfall tối đa là Copt - Cmin
                max_shortfall = Copt if not nurses else Copt - Cmin

                # Nếu không có khả năng thiếu hụt (ví dụ Cmin = Copt), bỏ qua
                if max_shortfall <= 0:
                    continue

                # Tạo các biến phạt cho sự thiếu hụt tiềm năng
                penalty_vars = []
                for j in range(max_shortfall):
                    # get_variable sẽ tự động tăng counter và cập nhật dicts
                    p_var = get_variable(f"penalty_s1_{d}_{s}_{sk}_{j}")
                    penalty_vars.append(p_var)

                # --- RÀNG BUỘC CỨNG: sum(nurses) + sum(penalty_vars) >= Copt ---
                combined_vars = nurses + penalty_vars

                # Xử lý trường hợp không có biến nào cả nhưng Copt > 0 (không thể thỏa mãn)
                if not combined_vars and Copt > 0:
                    # Thêm một mệnh đề cứng không thể thỏa mãn để báo lỗi
                    print(
                        f"CẢNH BÁO: Không thể đáp ứng Copt={Copt} cho d={d}, s={s}, sk={sk} vì không có y tá/biến phạt.")
                    hard_clauses.append("1 0")  # Thêm x và -x để tạo UNSAT
                    # Nên thêm biến số 1 vào dict nếu chưa có
                    hard_clauses.append("-1 0")
                    if 'dummy_unsat' not in variable_dict:
                        variable_dict['dummy_unsat'] = 1
                        reverse_variable_dict[1] = 'dummy_unsat'
                    continue  # Chuyển sang lần lặp tiếp theo

                # Nếu có biến, sử dụng bộ mã hóa at_least_k
                elif combined_vars:
                    # Sử dụng optilog encoder cho ràng buộc cứng >= Copt
                    # max_var nên là giá trị counter hiện tại TRỪ 1
                    current_top_var = counter - 1
                    top_var, formula = Encoder.at_least_k(
                        combined_vars, Copt, max_var=current_top_var, encoding=optilog_encoding)

                    # Thêm các mệnh đề được tạo ra vào danh sách hard_clauses TOÀN CỤC
                    for clause in formula:
                        hard_clauses.append(" ".join(map(str, clause)) + " 0")

                    # Cập nhật counter và dictionaries cho các biến phụ trợ MỚI
                    # được tạo ra BÊN TRONG bộ mã hóa at_least_k
                    for var_idx in range(current_top_var + 1, top_var + 1):
                        # Tạo tên duy nhất cho biến phụ trợ của encoder
                        aux_encoder_name = f"aux_s1_enc_{d}_{s}_{sk}_{var_idx}"
                        if var_idx not in reverse_variable_dict:  # Chỉ thêm nếu chưa tồn tại
                            variable_dict[aux_encoder_name] = var_idx
                            reverse_variable_dict[var_idx] = aux_encoder_name
                        # else: # Nếu biến đã tồn tại, có thể có lỗi logic hoặc trùng lặp ID
                        #     print(f"Cảnh báo: Biến phụ trợ {var_idx} đã tồn tại.")

                    # Cập nhật counter toàn cục lên giá trị cao nhất mới được sử dụng bởi encoder
                    counter = top_var + 1  # Rất quan trọng!

                # --- RÀNG BUỘC MỀM: Phạt việc sử dụng các biến phạt ---
                for p_var in penalty_vars:
                    # Thêm (-p_var) như một mệnh đề mềm vào danh sách cục bộ của hàm này
                    soft_clauses_for_S1.append((penalty_weight, f"-{p_var} 0"))

    # Trả về danh sách các mệnh đề mềm ĐÃ được tạo bởi logic S1 này
    return soft_clauses_for_S1


def constraint_S1_old_optilog(N, D, S, SK, weekdays, nurse_skills, penalty_weight):
    global counter, variable_dict, reverse_variable_dict
    soft_clauses = []

    for d in range(D):
        for s in S:
            for sk in SK:
                Copt = get_Copt(weekdays, d, s, sk)
                Cmin = get_Cmin(weekdays, d, s, sk)
                if Copt - Cmin <= 0:
                    continue

                # Penalize each missing nurse below Copt (soft constraint)
                if Copt > 0:
                    nurses = [get_variable(f"x_{n}_{d}_{s}_{sk}") for n in range(
                        N) if sk in nurse_skills.get(n, [])]
                    max_var_copt, formula = Encoder.at_least_k(
                        nurses, Copt, max_var=len(variable_dict), encoding=optilog_encoding)
                    for clause in formula:
                        soft_clauses.append(
                            (penalty_weight, " ".join(map(str, clause)) + " 0"))

                    for var in range(len(variable_dict) + 1, max_var_copt + 1):
                        variable_dict[f"aux_cmax{var}"] = var
                        reverse_variable_dict[var] = f"aux_cmax{var}"

                    counter = max_var_copt + 1
    return soft_clauses
# S4. Preferences(10)


def constraint_S4_SOR(weekdays, nurse_name_to_index, penalty_weight):
    soft_clauses = []
    day_mapping = {0: 'Monday', 1: 'Tuesday', 2: 'Wednesday',
                   3: 'Thursday', 4: 'Friday', 5: 'Saturday', 6: 'Sunday'}

    for week_index, weekday in enumerate(weekdays):
        shift_off_requests = weekday['shiftOffRequests']

        for request in shift_off_requests:
            nurse_name = request['nurse']
            shift_type = request['shiftType']
            day = request['day']

            # Find the nurse index
            nurse_index = nurse_name_to_index.get(nurse_name, None)

            # Find the day index
            day_index = next(
                (d for d, day_name in day_mapping.items() if day_name == day), None) + week_index * 7

            if shift_type == "Any":
                var = get_variable(f"e_{nurse_index}_{day_index}")
                soft_clauses.append((penalty_weight, f"-{var} 0"))
            else:
                # for sk in nurse_skills.get(nurse_index, []):
                # var = get_variable(
                #     f"x_{nurse_index}_{day_index}_{shift_type}_{sk}")
                # soft_clauses.append((penalty_weight, f"-{var} 0"))
                var = get_variable(
                    f"o_{nurse_index}_{day_index}_{shift_type}")
                soft_clauses.append((penalty_weight, f"-{var} 0"))

    return soft_clauses

# S5: Complete Weekend


def constraint_S5(N, D, nurse_contracts, contracts, penalty_weight):
    soft_clauses = []
    weekends = []  # List to store weekend days

    # Determine weekends dynamically
    for d in range(D):
        day_of_week = d % 7
        # Assuming Saturday (5) and Sunday (6) as weekends
        if day_of_week in [5, 6]:
            weekends.append(d)

    for n in range(N):
        contract_id = nurse_contracts[n]
        contract = contracts[contract_id]

        if contract.get('completeWeekends', 0) == 1:
            for i in range(0, len(weekends), 2):
                if i + 1 < len(weekends):
                    d1, d2 = weekends[i], weekends[i + 1]
                    # Create variables for working on both weekend days
                    w1 = get_variable(f"e_{n}_{d1}")
                    w2 = get_variable(f"e_{n}_{d2}")

                    # Add clauses to ensure the nurse works both days or none
                    soft_clauses.append((penalty_weight, f"-{w1} {w2} 0"))
                    soft_clauses.append((penalty_weight, f"{w1} -{w2} 0"))

    return soft_clauses


def constraint_S2_cons_work_day(weekdays, nurse_history, nurse_name_to_index, nurse_contracts, contracts, penalty_weight):
    soft_clauses = []
    horizon_length = len(weekdays) * 7

    for nurse in nurse_history:
        nurse_id = nurse_name_to_index[nurse['nurse']]
        cons_working_days = nurse.get('numberOfConsecutiveWorkingDays', 0)

        contract_id = nurse_contracts[nurse_id]
        contract = contracts[contract_id]
        CW_max = contract.get('maximumNumberOfConsecutiveWorkingDays', 0)
        CW_min = contract.get('minimumNumberOfConsecutiveWorkingDays', 0)

        # CW_max
        if cons_working_days == 0:
            for d in range(horizon_length - CW_max):
                clause = []
                for j in range(CW_max + 1):
                    var = get_variable(f"e_{nurse_id}_{d + j}")
                    clause.append(f"-{var}")
                soft_clauses.append((penalty_weight, " ".join(clause) + " 0"))
        else:
            if cons_working_days >= CW_max:
                cons_working_days = CW_max

            for d in range(horizon_length - 1, CW_max - 1, -1):
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
        for d in range(horizon_length - CW_min + 1):
            clause = []
            today = get_variable(f"e_{nurse_id}_{d}")
            if d == 0:
                if cons_working_days == 0:
                    clause.append(f"-{today}")
                else:
                    continue
            else:
                yesterday = get_variable(f"e_{nurse_id}_{d - 1}")
                clause.append(f"-{today} {yesterday}")
            for j in range(1, CW_min):
                next_day = get_variable(f"e_{nurse_id}_{d + j}")
                soft_clauses.append(
                    (penalty_weight, " ".join(clause) + f" {next_day} 0"))

        last_days = [get_variable(f"e_{nurse_id}_{d}") for d in range(
            horizon_length - CW_min + 1, horizon_length, 1)]
        for (e1, e2) in combinations(last_days, 2):
            soft_clauses.append((penalty_weight, f"-{e1} {e2} 0"))
            soft_clauses.append((penalty_weight, f"{e1} -{e2} 0"))

        if cons_working_days != 0:
            if cons_working_days >= CW_min:
                continue
            else:
                needed_days = CW_min - cons_working_days
                for i in range(needed_days):
                    var = get_variable(f"e_{nurse_id}_{i}")
                    soft_clauses.append((penalty_weight, f"{var} 0"))

    return soft_clauses


def constraint_S2_cons_work_shift(weekdays, nurse_history, nurse_name_to_index, shift_types, penalty_weight):
    soft_clauses = []
    horizon_length = len(weekdays) * 7

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
                for d in range(horizon_length - CS_max):
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

                for d in range(horizon_length - 1, CS_max - 1, -1):
                    clause = []
                    for j in range(CS_max + 1):
                        var = get_variable(
                            f"o_{nurse_id}_{d - j}_{shift_id}")
                        clause.append(f"-{var}")
                    soft_clauses.append(
                        (penalty_weight, " ".join(clause) + " 0"))

                for d in range(CS_max - 1, -1, -1):
                    clause = []
                    if abs(d - CS_max) > cons_working_shifts:
                        break
                    for j in range(d + 1):
                        var = get_variable(
                            f"o_{nurse_id}_{d - j}_{shift_id}")
                        clause.append(f"-{var}")
                    soft_clauses.append(
                        (penalty_weight, " ".join(clause) + " 0"))

            # CS_min
            for d in range(horizon_length - CS_min + 1):
                clause = []
                today = get_variable(f"o_{nurse_id}_{d}_{shift_id}")
                if d == 0:
                    if cons_working_shifts == 0:
                        clause.append(f"-{today}")
                    else:
                        continue
                else:
                    yesterday = get_variable(
                        f"o_{nurse_id}_{d - 1}_{shift_id}")
                    clause.append(f"-{today} {yesterday}")
                for j in range(1, CS_min):
                    next_day = get_variable(f"o_{nurse_id}_{d + j}_{shift_id}")
                    soft_clauses.append(
                        (penalty_weight, " ".join(clause) + f" {next_day} 0"))

            last_shifts = [get_variable(f"o_{nurse_id}_{d}_{shift_id}") for d in range(
                horizon_length - CS_min + 1, horizon_length, 1)]
            for (o1, o2) in combinations(last_shifts, 2):
                soft_clauses.append((penalty_weight, f"-{o1} {o2} 0"))
                soft_clauses.append((penalty_weight, f"{o1} -{o2} 0"))

            if cons_working_shifts != 0:
                if cons_working_shifts >= CS_min:
                    continue
                else:
                    needed_days = CS_min - cons_working_shifts
                    for i in range(needed_days):
                        var = get_variable(f"o_{nurse_id}_{i}_{shift_id}")
                        soft_clauses.append((penalty_weight, f"{var} 0"))

    return soft_clauses


def constraint_S3(weekdays, nurse_history, nurse_name_to_index, nurse_contracts, contracts, penalty_weight):
    soft_clauses = []
    horizon_length = len(weekdays) * 7

    for nurse in nurse_history:
        nurse_id = nurse_name_to_index[nurse['nurse']]
        cons_working_days_off = nurse.get('numberOfConsecutiveDaysOff', 0)

        contract_id = nurse_contracts[nurse_id]
        contract = contracts[contract_id]
        CF_max = contract.get('maximumNumberOfConsecutiveDaysOff', 0)
        CF_min = contract.get('minimumNumberOfConsecutiveDaysOff', 0)

        # CF_max
        if cons_working_days_off == 0:
            for d in range(horizon_length - CF_max):
                clause = []
                for j in range(CF_max + 1):
                    var = get_variable(f"e_{nurse_id}_{d + j}")
                    clause.append(f"{var}")
                soft_clauses.append((penalty_weight, " ".join(clause) + " 0"))
        else:
            if cons_working_days_off >= CF_max:
                cons_working_days_off = CF_max

            for d in range(horizon_length - 1, CF_max - 1, -1):
                clause = []
                for j in range(CF_max + 1):
                    var = get_variable(f"e_{nurse_id}_{d - j}")
                    clause.append(f"{var}")
                soft_clauses.append((penalty_weight, " ".join(clause) + " 0"))

            for d in range(CF_max - 1, -1, -1):
                clause = []
                if abs(d - CF_max) > cons_working_days_off:
                    break
                for j in range(d + 1):
                    var = get_variable(f"e_{nurse_id}_{d - j}")
                    clause.append(f"{var}")
                soft_clauses.append((penalty_weight, " ".join(clause) + " 0"))

        # CF_min
        for d in range(horizon_length - CF_min + 1):
            clause = []
            today = get_variable(f"e_{nurse_id}_{d}")
            if d == 0:
                if cons_working_days_off == 0:
                    clause.append(f"{today}")
                else:
                    continue
            else:
                yesterday = get_variable(f"e_{nurse_id}_{d - 1}")
                clause.append(f"{today} -{yesterday}")
            for j in range(1, CF_min):
                next_day = get_variable(f"e_{nurse_id}_{d + j}")
                soft_clauses.append(
                    (penalty_weight, " ".join(clause) + f" -{next_day} 0"))

        last_days = [get_variable(f"e_{nurse_id}_{d}") for d in range(
            horizon_length - CF_min + 1, horizon_length, 1)]
        for (e1, e2) in combinations(last_days, 2):
            soft_clauses.append((penalty_weight, f"-{e1} {e2} 0"))
            soft_clauses.append((penalty_weight, f"{e1} -{e2} 0"))

        if cons_working_days_off != 0:
            if cons_working_days_off >= CF_min:
                continue
            else:
                needed_days = CF_min - cons_working_days_off
                for i in range(needed_days):
                    var = get_variable(f"e_{nurse_id}_{i}")
                    soft_clauses.append((penalty_weight, f"-{var} 0"))
    return soft_clauses

# Constraint Total Weekends
def constraint_total_weekends_new_optilog(N, W, nurse_contracts, contracts, penalty_weight):
    """
    Sửa đổi để sử dụng biến phạt phụ trợ cho ràng buộc maximumNumberOfWorkingWeekends.
    Sử dụng phép biến đổi sang at_least_k với biến phủ định phụ trợ.
    Thêm các mệnh đề cứng cần thiết vào hard_clauses toàn cục.
    """
    global counter, hard_clauses, variable_dict, reverse_variable_dict

    soft_clauses_for_S7 = []

    for n in range(N):
        contract_id = nurse_contracts[n]
        contract = contracts[contract_id]
        max_weekends = contract.get('maximumNumberOfWorkingWeekends', W + 1)

        if max_weekends < W:  # Chỉ mã hóa nếu có giới hạn thực sự
            weekend_vars_q = [get_variable(f"q_{n}_{w}") for w in range(W)]
            num_weekend_vars = len(weekend_vars_q)

            if not weekend_vars_q or num_weekend_vars <= max_weekends:
                continue  # Không thể vi phạm

            # --- Mã hóa sum(q_n_w) <= max_weekends ---
            # Biến đổi: sum(-q_n_w) >= num_weekend_vars - max_weekends
            target_atleast_k_prime = num_weekend_vars - max_weekends

            # 1. Tạo biến phạt cho việc *không* đạt được target_atleast_k_prime
            #    Số lượng phạt cần = target_atleast_k_prime (mức thiếu hụt tối đa của sum(-q))
            #    Nhưng số lượng phạt cũng tương ứng với mức vượt quá tối đa của sum(q)
            num_penalty = num_weekend_vars - max_weekends  # = target_atleast_k_prime
            penalty_vars_excess = []
            if num_penalty > 0:
                for j in range(num_penalty):
                    # Đặt tên rõ ràng là phạt cho việc vượt quá <= K
                    p_var = get_variable(f"penalty_s7_excess_{n}_{j}")
                    penalty_vars_excess.append(p_var)

            # 2. Tạo biến phụ trợ cho phủ định (-q_n_w)
            negated_q_vars_helper = []
            # Cần thêm các mệnh đề cứng định nghĩa các biến phủ định này
            for w_idx, q_var in enumerate(weekend_vars_q):
                q_var_name = reverse_variable_dict[q_var]  # Lấy tên gốc
                neg_q_helper_name = f"neg_{q_var_name}"
                neg_q_helper_var = get_variable(neg_q_helper_name)
                negated_q_vars_helper.append(neg_q_helper_var)

                # Thêm mệnh đề cứng: neg_q <=> NOT q
                # (-neg_q V -q) AND (neg_q V q)
                hard_clauses.append(f"-{neg_q_helper_var} -{q_var} 0")
                hard_clauses.append(f"{neg_q_helper_var} {q_var} 0")

            # 3. Ràng buộc CỨNG: sum(neg_q_helpers) + sum(penalty_vars_excess) >= target_atleast_k_prime
            combined_vars_for_atleast = negated_q_vars_helper + penalty_vars_excess

            # Đảm bảo target_atleast_k_prime >= 0 (luôn đúng do cách tính)
            if target_atleast_k_prime >= 0 and combined_vars_for_atleast:
                current_top_var = counter - 1
                top_var, formula_hard = Encoder.at_least_k(
                    combined_vars_for_atleast,
                    target_atleast_k_prime,
                    max_var=current_top_var,
                    encoding=optilog_encoding
                )

                for clause in formula_hard:
                    hard_clauses.append(" ".join(map(str, clause)) + " 0")

                # Cập nhật biến phụ trợ của encoder
                for var_idx in range(current_top_var + 1, top_var + 1):
                    aux_encoder_name = f"aux_s7_enc_{n}_{var_idx}"
                    if var_idx not in reverse_variable_dict:
                        variable_dict[aux_encoder_name] = var_idx
                        reverse_variable_dict[var_idx] = aux_encoder_name
                counter = max(counter, top_var + 1)  # Cập nhật counter

            # 4. Ràng buộc MỀM cho biến phạt
            for p_var in penalty_vars_excess:
                soft_clauses_for_S7.append((penalty_weight, f"-{p_var} 0"))

    return soft_clauses_for_S7


def constraint_total_weekends_old_optilog(N, W, nurse_contracts, contracts, penalty_weight):
    global counter, variable_dict, reverse_variable_dict
    soft_clauses = []

    for n in range(N):
        contract_id = nurse_contracts[n]
        contract = contracts[contract_id]
        max_weekends = contract.get('maximumNumberOfWorkingWeekends', 0)

        if max_weekends > 0:
            weekend_vars = [get_variable(f"q_{n}_{w}") for w in range(W)]
            max_var, formula = Encoder.at_most_k(
                weekend_vars, max_weekends, max_var=len(variable_dict), encoding=optilog_encoding)

            for clause in formula:
                soft_clauses.append(
                    (penalty_weight, " ".join(map(str, clause)) + " 0"))

            for var in range(len(variable_dict) + 1, max_var + 1):
                variable_dict[f"aux_cwmax{var}"] = var
                reverse_variable_dict[var] = f"aux_cwmax{var}"

            counter = max_var + 1

    return soft_clauses

# Constraint Total Assignments
def constraint_total_assignments_new_optilog(N, D, nurse_contracts, contracts, penalty_weight):
    """
    Sửa đổi để sử dụng biến phạt phụ trợ cho min/max total assignments.
    Sử dụng phép biến đổi sang at_least_k cho phần max.
    Thêm các mệnh đề cứng cần thiết vào hard_clauses toàn cục.
    """
    global counter, hard_clauses, variable_dict, reverse_variable_dict

    soft_clauses_for_S6 = []

    for n in range(N):
        contract_id = nurse_contracts[n]
        contract = contracts[contract_id]
        max_assign = contract.get('maximumNumberOfAssignments', D + 1)
        min_assign = contract.get('minimumNumberOfAssignments', 0)

        assignment_vars_e = [get_variable(f"e_{n}_{d}") for d in range(D)]
        num_assign_vars = len(assignment_vars_e)

        if not assignment_vars_e:
            continue

        # --- Phần Max assignments: sum(e_n_d) <= max_assign ---
        if max_assign < num_assign_vars:  # Chỉ mã hóa nếu có giới hạn thực sự
            target_atleast_k_prime_max = num_assign_vars - max_assign  # K' cho phần max

            # 1. Tạo biến phạt vượt quá max_assign
            num_penalty_max = num_assign_vars - max_assign  # = target_atleast_k_prime_max
            penalty_vars_max = []
            if num_penalty_max > 0:
                for j in range(num_penalty_max):
                    p_var = get_variable(f"penalty_s6_max_{n}_{j}")
                    penalty_vars_max.append(p_var)

            # 2. Tạo biến phụ trợ phủ định (-e_n_d)
            negated_e_vars_helper = []
            for d_idx, e_var in enumerate(assignment_vars_e):
                e_var_name = reverse_variable_dict[e_var]
                neg_e_helper_name = f"neg_{e_var_name}"
                neg_e_helper_var = get_variable(neg_e_helper_name)
                negated_e_vars_helper.append(neg_e_helper_var)
                # Định nghĩa cứng: neg_e <=> NOT e
                hard_clauses.append(f"-{neg_e_helper_var} -{e_var} 0")
                hard_clauses.append(f"{neg_e_helper_var} {e_var} 0")

            # 3. Ràng buộc CỨNG: sum(neg_e_helpers) + sum(penalty_vars_max) >= target_atleast_k_prime_max
            combined_vars_max = negated_e_vars_helper + penalty_vars_max
            if target_atleast_k_prime_max >= 0 and combined_vars_max:
                current_top_var = counter - 1
                top_var, formula_max_hard = Encoder.at_least_k(
                    combined_vars_max,
                    target_atleast_k_prime_max,
                    max_var=current_top_var,
                    encoding=optilog_encoding
                )
                for clause in formula_max_hard:
                    hard_clauses.append(" ".join(map(str, clause)) + " 0")
                # Cập nhật biến encoder
                for var_idx in range(current_top_var + 1, top_var + 1):
                    aux_encoder_name = f"aux_s6_max_enc_{n}_{var_idx}"
                    if var_idx not in reverse_variable_dict:
                        variable_dict[aux_encoder_name] = var_idx
                        reverse_variable_dict[var_idx] = aux_encoder_name
                counter = max(counter, top_var + 1)

            # 4. Ràng buộc MỀM cho biến phạt max
            for p_var in penalty_vars_max:
                soft_clauses_for_S6.append((penalty_weight, f"-{p_var} 0"))

        # --- Phần Min assignments: sum(e_n_d) >= min_assign ---
        # (Phần này giữ nguyên logic từ lần sửa trước, đã đúng)
        if min_assign > 0:
            max_shortfall = min_assign  # Thiếu tối đa là min_assign
            if max_shortfall > 0:
                # 1. Tạo biến phạt thiếu hụt
                penalty_vars_min = []
                for j in range(max_shortfall):
                    p_var = get_variable(f"penalty_s6_min_{n}_{j}")
                    penalty_vars_min.append(p_var)

                # 2. Ràng buộc CỨNG: sum(e_n_d) + sum(penalty_vars_min) >= min_assign
                combined_vars_min = assignment_vars_e + penalty_vars_min
                if combined_vars_min:  # Chỉ mã hóa nếu có biến
                    current_top_var = counter - 1
                    top_var, formula_min_hard = Encoder.at_least_k(
                        combined_vars_min,
                        min_assign,
                        max_var=current_top_var,
                        encoding=optilog_encoding
                    )
                    for clause in formula_min_hard:
                        hard_clauses.append(" ".join(map(str, clause)) + " 0")
                    # Cập nhật biến encoder
                    for var_idx in range(current_top_var + 1, top_var + 1):
                        aux_encoder_name = f"aux_s6_min_enc_{n}_{var_idx}"
                        if var_idx not in reverse_variable_dict:
                            variable_dict[aux_encoder_name] = var_idx
                            reverse_variable_dict[var_idx] = aux_encoder_name
                    counter = max(counter, top_var + 1)

                # 3. Ràng buộc MỀM cho biến phạt min
                for p_var in penalty_vars_min:
                    soft_clauses_for_S6.append((penalty_weight, f"-{p_var} 0"))

    return soft_clauses_for_S6


def constraint_total_assignments_old_optilog(N, D, nurse_contracts, contract, penalty_weight):
    global counter, variable_dict, reverse_variable_dict
    soft_clauses = []

    for n in range(N):
        contract_id = nurse_contracts[n]
        contract = contracts[contract_id]
        max_assign = contract.get('maximumNumberOfAssignments', 0)
        min_assign = contract.get('minimumNumberOfAssignments', 0)

        # Max assignments:
        if max_assign > 0:
            assignment_vars = [get_variable(
                f"e_{n}_{d}") for d in range(D)]
            max_var, formula = Encoder.at_most_k(
                assignment_vars, max_assign, max_var=len(variable_dict), encoding=optilog_encoding)
            for clause in formula:
                soft_clauses.append(
                    (penalty_weight, " ".join(map(str, clause)) + " 0"))

            for var in range(len(variable_dict) + 1, max_var + 1):
                variable_dict[f"aux_max_assign{var}"] = var
                reverse_variable_dict[var] = f"aux_max_assign{var}"

            counter = max_var + 1

        # Min assignments:
        if min_assign > 0:
            assignment_vars = [get_variable(
                f"e_{n}_{d}") for d in range(D)]
            min_var, formula = Encoder.at_least_k(
                assignment_vars, min_assign, max_var=len(variable_dict), encoding=optilog_encoding)

            for clause in formula:
                soft_clauses.append(
                    (penalty_weight, " ".join(map(str, clause)) + " 0"))

            for var in range(len(variable_dict) + 1, min_var + 1):
                variable_dict[f"aux_min_assign{var}"] = var
                reverse_variable_dict[var] = f"aux_min_assign{var}"

            counter = min_var + 1

    return soft_clauses

def run_tt_open_wbo_inc(wcnf_path, timeout, output_file):
    """
    Run the tt-open-wbo-inc solver on the given WCNF file.

    Args:
        wcnf_path (str): Path to the WCNF file.
        timeout (int): Timeout in seconds.
        output_file (str): Path to save the solver output.

    Returns:
        list: A list of solution variables if a solution is found, otherwise None.
    """
    global reverse_variable_dict
    try:
        # cmd = ["timeout", str(timeout),
        #        "./tt-open-wbo-inc-Glucose4_1_static", wcnf_path]
        cmd = ["timeout", str(timeout),
               "./tt-open-wbo-inc-IntelSATSolver_static", wcnf_path]
        result = subprocess.run(cmd, capture_output=True, text=True)

        # Save the solver output to the specified file
        with open(output_file, 'w') as f:
            f.write(result.stdout)
            if result.stderr:
                f.write(result.stderr)

        output = result.stdout
        with open("log.txt", 'w') as f:
            f.write(output)

        # Check the solver output for a solution
        if "v " in output:  # Look for the binary solution line
            solution_lines = [
                line.strip() for line in output.splitlines() if line.startswith("v ")
            ]
            binary_solution = "".join(solution_lines).replace(
                "v ", "")  # Concatenate and remove 'v '
            decimal_solution = []
            for index, char in enumerate(binary_solution, start=1):
                if char == "1":
                    decimal_solution.append(index)  # Positive number
                elif char == "0":
                    decimal_solution.append(-index)  # Negative number

            # Map only positive integers using reverse_variable_dict
            mapped_solution = [
                reverse_variable_dict[var] for var in decimal_solution if var > 0 and var in reverse_variable_dict
            ]
            return mapped_solution
        elif "s UNSATISFIABLE" in output:
            print("The problem is unsatisfiable.")
            return None
        else:
            print("No valid solution found in the output.")
            return None

    except Exception as e:
        print(f"An error occurred while running tt-open-wbo-inc: {e}")
        return None


def decode_solution(solution, nurse_name_to_index, start_day, end_day):
    assignments = []
    index_to_nurse_name = {v: k for k, v in nurse_name_to_index.items()}
    day_mapping = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    for var in solution:
        parts = var.split("_")
        if parts[0] == 'x':
            nurse_id, day, shift, skill = parts[1], parts[2], parts[3], parts[4]
            day = int(day)
            if start_day <= day < end_day:
                nurse_name = index_to_nurse_name[int(nurse_id)]
                day_name = day_mapping[day % 7]
                assignments.append({
                    "nurse": nurse_name,
                    "day": day_name,
                    "shiftType": shift,
                    "skill": skill
                })
    return assignments


def export_cnf(filename="output.cnf", hard_clauses=[], soft_clauses=[], weight_hard=60):
    with open(filename, "w") as f:
        f.write(
            f"p wcnf {counter - 1} {len(hard_clauses) + len(soft_clauses)} {weight_hard}\n")
        for clause in hard_clauses:
            f.write(f"{weight_hard} {clause}\n")
        for weight, clause in soft_clauses:
            f.write(f"{weight} {clause}\n")


def export_cnf_custom_format(filename="output.cnf", hard_clauses=[], soft_clauses=[]):
    """
    Export CNF in a custom format where hard clauses are prefixed with 'h'.
    """
    with open(filename, "w") as f:
        # Write hard clauses with 'h' prefix
        for clause in hard_clauses:
            f.write(f"h {clause}\n")

        # Write soft clauses without 'h' prefix
        for weight, clause in soft_clauses:
            f.write(f"{weight} {clause}\n")


def process_log_file(log_file_path, output_file_path):
    """
    Process the log file to convert binary numbers (0 and 1) to decimal numbers.
    Each 0 is treated as a negative number, and each 1 is treated as a positive number.
    The result is saved to an output file.

    Args:
        log_file_path (str): Path to the input log file.
        output_file_path (str): Path to the output file where results will be saved.
    """
    try:
        with open(log_file_path, "r") as log_file:
            # Read the entire file and strip whitespace
            binary_data = log_file.read().strip()

        # Convert binary data to decimal numbers
        decimal_numbers = []
        for index, char in enumerate(binary_data, start=1):  # Index starts at 1
            if char == "1":
                decimal_numbers.append(index)  # Positive number
            elif char == "0":
                decimal_numbers.append(-index)  # Negative number

        # Save the result to the output file
        with open(output_file_path, "w") as output_file:
            output_file.write(" ".join(map(str, decimal_numbers)))

        print(f"Processed log file saved to: {output_file_path}")

    except Exception as e:
        print(f"An error occurred: {e}")


def save_solution(assignments, scenario_id, week_index, solution_file):
    solution = {
        "scenario": scenario_id,
        "week": week_index,
        "assignments": assignments
    }
    with open(solution_file, 'w') as f:
        json.dump(solution, f, indent=4)


def export_variable_mapping(filename="variable_mapping.txt"):
    with open(filename, "w") as f:
        for var_id, var_name in reverse_variable_dict.items():
            f.write(f"{var_id}: {var_name}\n")


def print_variable_counts():
    x_count = sum(1 for var in variable_dict if var.startswith('x_'))
    o_count = sum(1 for var in variable_dict if var.startswith('o_'))
    e_count = sum(1 for var in variable_dict if var.startswith('e_'))
    q_count = sum(1 for var in variable_dict if var.startswith('q_'))
    aux_cmax_count = sum(
        1 for var in variable_dict if var.startswith('aux_cmax'))
    aux_cmin_count = sum(
        1 for var in variable_dict if var.startswith('aux_cmin'))
    aux_min_assign_count = sum(
        1 for var in variable_dict if var.startswith('aux_min_assign'))
    aux_max_assign_count = sum(
        1 for var in variable_dict if var.startswith('aux_max_assign'))
    aux_cwmax_count = sum(
        1 for var in variable_dict if var.startswith('aux_cwmax'))
    auxvarsc_count = sum(
        1 for var in variable_dict if var.startswith('auxvarsc'))

    print(f"Number of x variables: {x_count}")
    print(f"Number of o variables: {o_count}")
    print(f"Number of e variables: {e_count}")
    print(f"Number of q variables: {q_count}")
    print(f"Number of aux_cmax variables: {aux_cmax_count}")
    print(f"Number of aux_cmin variables: {aux_cmin_count}")
    print(f"Number of aux_max_assign variables: {aux_max_assign_count}")
    print(f"Number of aux_min_assign variables: {aux_min_assign_count}")
    print(f"Number of aux_cwmax variables: {aux_cwmax_count}")
    print(f"Number of auxvarsc variables: {auxvarsc_count}")


def read_solution_file(file_path):
    with open(file_path, 'r') as file:
        content = file.read()
    return [int(num) for num in content.split()]


def parse_arguments():
    """
    Parse command-line arguments for the Nurse Rostering Problem Solver.
    """
    parser = argparse.ArgumentParser(
        description="Nurse Rostering Problem Solver")
    parser.add_argument('--sce', required=True, help='Scenario File')
    parser.add_argument('--his', required=True, help='Initial History File')
    parser.add_argument('--weeks', required=True,
                        nargs='+', help='Weeks Data Files')
    parser.add_argument('--sol', required=True, help='Solution Folder')
    parser.add_argument('--timeout', type=float, help='Timeout in Seconds')
    return parser.parse_args()


def generate_hard_clauses(N, D, S, SK, weekdays, nurse_skills, forbidden_shifts, nurse_history):
    """
    Generate hard clauses for the problem based on constraints.
    """
    global hard_clauses

    # Constraint H1: No overlapping shifts
    hard_clauses_H1 = constraint_H1(N, D, S)
    hard_clauses += hard_clauses_H1
    print(f"Number of clauses for H1: {len(hard_clauses_H1)}")

    # # Constraint H3: Forbidden shift successions
    hard_clauses_H3 = constraint_H3(N, D, forbidden_shifts, nurse_history)
    hard_clauses += hard_clauses_H3
    print(f"Number of clauses for H3: {len(hard_clauses_H3)}")

    # Constraint H1&H3 (using SC)
    # hard_clauses_H1_H3 = constraint_H3_SC(
    #     N, D, S, forbidden_shifts, nurse_history, weekdays)
    # hard_clauses += hard_clauses_H1_H3
    # print(f"Number of clauses for H1_H3: {len(hard_clauses_H1_H3)}")

    # Auxiliary constraints
    hard_clauses_aux = constraint_aux(N, D, S, nurse_skills)
    hard_clauses += hard_clauses_aux
    print(f"Number of clauses for aux: {len(hard_clauses_aux)}")


    # Constraint H2: Minimum coverage (optilog)
    # hard_clauses_H2 = constraint_optilog_H2(
    #     N, D, S, SK, weekdays, nurse_skills)
    # hard_clauses += hard_clauses_H2
    # print(f"Number of clauses for H2 old optilog: {len(hard_clauses_H2)}")

    hard_clauses_H2 = constraint_new_optilog_H2(
        N, D, S, SK, weekdays, nurse_skills)
    hard_clauses += hard_clauses_H2
    print(f"Number of clauses for H2 new optilog: {len(hard_clauses_H2)}")

    return hard_clauses


def generate_soft_clauses(N, D, S, SK, W, weekdays, nurse_skills, nurse_name_to_index, nurse_contracts, contracts, nurse_history, shift_types):
    """
    Generate soft clauses for the problem based on preferences and penalties.
    """
    soft_clauses = []

    # # Soft constraint S1 (using old optilog): Optimal coverage
    # soft_clauses_S1 = constraint_S1_old_optilog(
    #     N, D, S, SK, weekdays, nurse_skills, penalty_weight=30)
    # soft_clauses += soft_clauses_S1
    # print(
    #     f"Number of soft clauses for S1_old_optilog : {len(soft_clauses_S1)}")

    # Soft constraint S1 (using new optilog): Optimal coverage
    soft_clauses_S1 = constraint_S1_new_optilog(
        N, D, S, SK, weekdays, nurse_skills, penalty_weight=30)
    soft_clauses += soft_clauses_S1
    print(
        f"Number of soft clauses for S1_new_optilog : {len(soft_clauses_S1)}")

    # Soft constraint S5: Complete weekends
    soft_clauses_S5 = constraint_S5(
        N, D, nurse_contracts, contracts, penalty_weight=30)
    soft_clauses += soft_clauses_S5
    print(f"Number of soft clauses for S5: {len(soft_clauses_S5)}")

    # Soft constraint S4: Shift-off requests
    soft_clauses_S4_SOR = constraint_S4_SOR(
        weekdays, nurse_name_to_index, penalty_weight=10)
    soft_clauses += soft_clauses_S4_SOR
    print(f"Number of soft clauses for S4_SOR: {len(soft_clauses_S4_SOR)}")

    # Soft constraint S2: Consecutive working days
    soft_clauses_S2_cons_work_day = constraint_S2_cons_work_day(
        weekdays, nurse_history, nurse_name_to_index, nurse_contracts, contracts, penalty_weight=30)
    soft_clauses += soft_clauses_S2_cons_work_day
    print(
        f"Number of soft clauses for S2_cons_work_day: {len(soft_clauses_S2_cons_work_day)}")

    # Soft constraint S2: Consecutive working shifts
    soft_clauses_S2_cons_work_shift = constraint_S2_cons_work_shift(
        weekdays, nurse_history, nurse_name_to_index, shift_types, penalty_weight=15)
    soft_clauses += soft_clauses_S2_cons_work_shift
    print(
        f"Number of soft clauses for S2_cons_work_shift: {len(soft_clauses_S2_cons_work_shift)}")

    # Soft constraint S3: Consecutive days off
    soft_clauses_S3 = constraint_S3(
        weekdays, nurse_history, nurse_name_to_index, nurse_contracts, contracts, penalty_weight=30)
    soft_clauses += soft_clauses_S3
    print(f"Number of soft clauses for S3: {len(soft_clauses_S3)}")

    # # Soft constraint S7 (using old optilog): Total working weekends
    # soft_clauses_optilog_total_weekends = constraint_total_weekends_old_optilog(
    #     N, W, nurse_contracts, contracts, penalty_weight=30)
    # soft_clauses += soft_clauses_optilog_total_weekends
    # print(
    #     f"Number of soft clauses for old_optilog_total_weekends: {len(soft_clauses_optilog_total_weekends)}")

    # # Soft constraint S6 (using old optilog): Total assignments
    # soft_clauses_optilog_total_assignments = constraint_total_assignments_old_optilog(
    #     N, D, nurse_contracts, contracts, penalty_weight=20)
    # soft_clauses += soft_clauses_optilog_total_assignments
    # print(
    #     f"Number of soft clauses for old_optilog_total_assignments: {len(soft_clauses_optilog_total_assignments)}")

    # Soft constraint S7 (using new optilog): Total working weekends
    soft_clauses_optilog_total_weekends = constraint_total_weekends_new_optilog(
        N, W, nurse_contracts, contracts, penalty_weight=30)
    soft_clauses += soft_clauses_optilog_total_weekends
    print(
        f"Number of soft clauses for new_optilog_total_weekends: {len(soft_clauses_optilog_total_weekends)}")

    # Soft constraint S6 (using new optilog): Total assignments
    soft_clauses_optilog_total_assignments = constraint_total_assignments_new_optilog(
        N, D, nurse_contracts, contracts, penalty_weight=20)
    soft_clauses += soft_clauses_optilog_total_assignments
    print(
        f"Number of soft clauses for new_optilog_total_assignments: {len(soft_clauses_optilog_total_assignments)}")

    return soft_clauses


def debug_s1_penalty(solution_vars, N, D, S, SK, weekdays, nurse_skills):
    """
    Kiểm tra và in thông tin debug cho các biến phạt của ràng buộc S1.

    Args:
        solution_vars (set): Tập hợp các tên biến dương trong lời giải cuối cùng.
        N, D, S, SK, weekdays, nurse_skills: Dữ liệu cần thiết để tính Copt.
    """
    print("\n--- DEBUGGING S1 PENALTY VARIABLES ---")
    total_s1_mismatches = 0
    total_expected_penalty_vars = 0
    total_actual_penalty_vars = 0

    # Tạo một bản đồ nhanh để tra cứu biến nào có trong lời giải
    # solution_set = set(solution_vars) # Giả sử solution_vars đã là set rồi

    for d in range(D):
        for s in S:
            for sk in SK:
                Copt = get_Copt(weekdays, d, s, sk)
                Cmin = get_Cmin(weekdays, d, s, sk)

                # Chỉ kiểm tra các trường hợp mà S1 có thể áp dụng (Copt > Cmin)
                if Copt <= Cmin:
                    continue

                # Lấy các biến y tá và đếm số y tá thực tế được phân công
                actual_nurses = 0
                relevant_nurse_vars = []
                for n in range(N):
                    if sk in nurse_skills.get(n, []):
                        nurse_var_name = f"x_{n}_{d}_{s}_{sk}"
                        relevant_nurse_vars.append(nurse_var_name)
                        # Kiểm tra xem biến y tá có trong lời giải không
                        if nurse_var_name in solution_vars:
                            actual_nurses += 1

                # Tính toán thiếu hụt dự kiến
                expected_shortfall = 0
                if actual_nurses < Copt:
                    expected_shortfall = Copt - actual_nurses

                # Tính toán số lượng biến phạt tối đa có thể có cho yêu cầu này
                max_possible_shortfall = Copt if not relevant_nurse_vars else Copt - Cmin
                if max_possible_shortfall < 0:
                    max_possible_shortfall = 0  # Đảm bảo không âm

                # Đếm số biến phạt thực tế được bật trong lời giải
                actual_penalty_vars_on = 0
                relevant_penalty_vars = []
                for j in range(max_possible_shortfall):
                    # Lấy tên biến phạt đã dùng trong constraint_optilog_S1
                    penalty_var_name = f"penalty_s1_{d}_{s}_{sk}_{j}"
                    relevant_penalty_vars.append(penalty_var_name)
                    # Kiểm tra xem biến phạt có trong lời giải không
                    if penalty_var_name in solution_vars:
                        actual_penalty_vars_on += 1

                # So sánh và báo cáo nếu có sự không khớp
                # Chỉ báo cáo nếu có sự thiếu hụt dự kiến HOẶC có biến phạt được bật (để bắt lỗi thừa)
                if expected_shortfall > 0 or actual_penalty_vars_on > 0:
                    is_match = (expected_shortfall == actual_penalty_vars_on)
                    status = "OK" if is_match else "MISMATCH"
                    total_expected_penalty_vars += expected_shortfall
                    total_actual_penalty_vars += actual_penalty_vars_on

                    if not is_match:
                        total_s1_mismatches += 1
                        print(f"[{status}] Day={d}, Shift={s}, Skill={sk}: "
                              f"Copt={Copt}, ActualNurses={actual_nurses}, "
                              f"ExpectedShortfall={expected_shortfall}, "
                              f"ActualPenaltyVarsON={actual_penalty_vars_on}")
                        # Tùy chọn: In ra các biến y tá và biến phạt liên quan để debug sâu hơn
                        print(f"   Relevant Nurses: {relevant_nurse_vars}")
                        print(f"   Relevant Penalty: {relevant_penalty_vars}")
                        print(
                            f"   Solution Vars Subset (Penalty): {[p for p in relevant_penalty_vars if p in solution_vars]}")

    print("--- S1 DEBUG SUMMARY ---")
    print(f"Total Mismatches Found: {total_s1_mismatches}")
    print(
        f"Total Expected Penalty Variables ON (based on shortfall): {total_expected_penalty_vars}")
    print(
        f"Total Actual Penalty Variables ON (in solution): {total_actual_penalty_vars}")
    if total_s1_mismatches == 0:
        print("S1 Penalty mechanism seems to be working correctly.")
    else:
        print("Potential issues found in S1 penalty mechanism or its interaction.")
    print("------------------------------------")


def debug_s7_penalty(solution_vars, N, W, nurse_contracts, contracts):
    """
    Kiểm tra và in thông tin debug cho các biến phạt của ràng buộc S7 (Max Working Weekends).
    """
    print("\n--- DEBUGGING S7 PENALTY VARIABLES (Max Weekends) ---")
    total_s7_mismatches = 0
    total_expected_penalty_vars = 0
    total_actual_penalty_vars = 0
    # solution_set = set(solution_vars) # Giả sử đã là set

    for n in range(N):
        contract_id = nurse_contracts[n]
        contract = contracts[contract_id]
        max_weekends = contract.get('maximumNumberOfWorkingWeekends', W + 1)

        # Chỉ kiểm tra nếu có giới hạn thực sự
        if max_weekends < W:
            weekend_vars_q_names = [f"q_{n}_{w}" for w in range(W)]
            num_weekend_vars = len(weekend_vars_q_names)

            # Đếm số cuối tuần thực tế làm việc
            actual_weekends = 0
            for q_var_name in weekend_vars_q_names:
                if q_var_name in solution_vars:
                    actual_weekends += 1

            # Tính số cuối tuần vượt quá dự kiến
            expected_excess = 0
            if actual_weekends > max_weekends:
                expected_excess = actual_weekends - max_weekends

            # Đếm số biến phạt thực tế được bật
            actual_penalty_vars_on = 0
            num_penalty_possible = num_weekend_vars - max_weekends
            relevant_penalty_vars = []
            if num_penalty_possible > 0:
                for j in range(num_penalty_possible):
                    # Dùng tên biến phạt đã dùng trong hàm constraint_optilog_total_weekends
                    penalty_var_name = f"penalty_s7_excess_{n}_{j}"
                    relevant_penalty_vars.append(penalty_var_name)
                    if penalty_var_name in solution_vars:
                        actual_penalty_vars_on += 1

            # So sánh và báo cáo nếu có sự không khớp
            if expected_excess > 0 or actual_penalty_vars_on > 0:
                is_match = (expected_excess == actual_penalty_vars_on)
                status = "OK" if is_match else "MISMATCH"
                total_expected_penalty_vars += expected_excess
                total_actual_penalty_vars += actual_penalty_vars_on

                if not is_match:
                    total_s7_mismatches += 1
                    print(f"[{status}] Nurse={n}: MaxWeekends={max_weekends}, ActualWeekends={actual_weekends}, "
                          f"ExpectedExcess={expected_excess}, ActualPenaltyVarsON={actual_penalty_vars_on}")
                    print(f"   Relevant Penalty: {relevant_penalty_vars}")
                    print(
                        f"   Solution Vars Subset (Penalty): {[p for p in relevant_penalty_vars if p in solution_vars]}")

    print("--- S7 DEBUG SUMMARY ---")
    print(f"Total Mismatches Found: {total_s7_mismatches}")
    print(
        f"Total Expected Penalty Variables ON (based on excess): {total_expected_penalty_vars}")
    print(
        f"Total Actual Penalty Variables ON (in solution): {total_actual_penalty_vars}")
    if total_s7_mismatches == 0:
        print("S7 Max Weekends Penalty mechanism seems to be working correctly.")
    else:
        print("Potential issues found in S7 Max Weekends penalty mechanism.")
    print("------------------------------------")


def debug_s6_penalty(solution_vars, N, D, nurse_contracts, contracts):
    """
    Kiểm tra và in thông tin debug cho các biến phạt của ràng buộc S6 (Min/Max Total Assignments).
    """
    print("\n--- DEBUGGING S6 PENALTY VARIABLES (Min/Max Assignments) ---")
    total_s6_mismatches_max = 0
    total_s6_mismatches_min = 0
    total_expected_penalty_max = 0
    total_actual_penalty_max = 0
    total_expected_penalty_min = 0
    total_actual_penalty_min = 0
    # solution_set = set(solution_vars) # Giả sử đã là set

    for n in range(N):
        contract_id = nurse_contracts[n]
        contract = contracts[contract_id]
        max_assign = contract.get('maximumNumberOfAssignments', D + 1)
        min_assign = contract.get('minimumNumberOfAssignments', 0)

        assignment_vars_e_names = [f"e_{n}_{d}" for d in range(D)]
        num_assign_vars = len(assignment_vars_e_names)

        if not assignment_vars_e_names:
            continue

        # Đếm số ca làm thực tế
        actual_assignments = 0
        for e_var_name in assignment_vars_e_names:
            if e_var_name in solution_vars:
                actual_assignments += 1

        # --- Kiểm tra Phần Max Assignments (<= max_assign) ---
        if max_assign < num_assign_vars:
            expected_excess_max = 0
            if actual_assignments > max_assign:
                expected_excess_max = actual_assignments - max_assign

            actual_penalty_vars_on_max = 0
            num_penalty_possible_max = num_assign_vars - max_assign
            relevant_penalty_vars_max = []
            if num_penalty_possible_max > 0:
                for j in range(num_penalty_possible_max):
                    # Dùng tên biến phạt đã dùng trong hàm constraint_optilog_total_assignments
                    penalty_var_name = f"penalty_s6_max_{n}_{j}"
                    relevant_penalty_vars_max.append(penalty_var_name)
                    if penalty_var_name in solution_vars:
                        actual_penalty_vars_on_max += 1

            if expected_excess_max > 0 or actual_penalty_vars_on_max > 0:
                is_match_max = (expected_excess_max ==
                                actual_penalty_vars_on_max)
                status_max = "OK" if is_match_max else "MISMATCH"
                total_expected_penalty_max += expected_excess_max
                total_actual_penalty_max += actual_penalty_vars_on_max

                if not is_match_max:
                    total_s6_mismatches_max += 1
                    print(f"[{status_max}] Nurse={n} (MAX): MaxAssign={max_assign}, ActualAssign={actual_assignments}, "
                          f"ExpectedExcess={expected_excess_max}, ActualPenaltyVarsON={actual_penalty_vars_on_max}")
                    print(
                        f"   Relevant Penalty Max: {relevant_penalty_vars_max}")
                    print(
                        f"   Solution Vars Subset (Penalty Max): {[p for p in relevant_penalty_vars_max if p in solution_vars]}")

        # --- Kiểm tra Phần Min Assignments (>= min_assign) ---
        if min_assign > 0:
            expected_shortfall_min = 0
            if actual_assignments < min_assign:
                expected_shortfall_min = min_assign - actual_assignments

            actual_penalty_vars_on_min = 0
            num_penalty_possible_min = min_assign  # Thiếu tối đa là min_assign
            relevant_penalty_vars_min = []
            if num_penalty_possible_min > 0:
                for j in range(num_penalty_possible_min):
                    # Dùng tên biến phạt đã dùng trong hàm constraint_optilog_total_assignments
                    penalty_var_name = f"penalty_s6_min_{n}_{j}"
                    relevant_penalty_vars_min.append(penalty_var_name)
                    if penalty_var_name in solution_vars:
                        actual_penalty_vars_on_min += 1

            if expected_shortfall_min > 0 or actual_penalty_vars_on_min > 0:
                is_match_min = (expected_shortfall_min ==
                                actual_penalty_vars_on_min)
                status_min = "OK" if is_match_min else "MISMATCH"
                total_expected_penalty_min += expected_shortfall_min
                total_actual_penalty_min += actual_penalty_vars_on_min

                if not is_match_min:
                    total_s6_mismatches_min += 1
                    print(f"[{status_min}] Nurse={n} (MIN): MinAssign={min_assign}, ActualAssign={actual_assignments}, "
                          f"ExpectedShortfall={expected_shortfall_min}, ActualPenaltyVarsON={actual_penalty_vars_on_min}")
                    print(
                        f"   Relevant Penalty Min: {relevant_penalty_vars_min}")
                    print(
                        f"   Solution Vars Subset (Penalty Min): {[p for p in relevant_penalty_vars_min if p in solution_vars]}")

    print("--- S6 DEBUG SUMMARY ---")
    print(f"Total Mismatches Found (Max): {total_s6_mismatches_max}")
    print(
        f"Total Expected Penalty Vars ON (Max): {total_expected_penalty_max}")
    print(f"Total Actual Penalty Vars ON (Max): {total_actual_penalty_max}")
    print(f"Total Mismatches Found (Min): {total_s6_mismatches_min}")
    print(
        f"Total Expected Penalty Vars ON (Min): {total_expected_penalty_min}")
    print(f"Total Actual Penalty Vars ON (Min): {total_actual_penalty_min}")
    if total_s6_mismatches_max == 0 and total_s6_mismatches_min == 0:
        print("S6 Min/Max Assignments Penalty mechanism seems to be working correctly.")
    else:
        print("Potential issues found in S6 Min/Max Assignments penalty mechanism.")
    print("------------------------------------")


def export_and_solve(args, hard_clauses, soft_clauses, nurse_name_to_index, weekdays, scenario, N, D, S, SK, W, nurse_skills, nurse_contracts, contracts):
    """
    Export the CNF file and solve the problem using the specified solver.
    """
    if not os.path.exists(args.sol):
        os.makedirs(args.sol)
    export_variable_mapping(filename=f"{args.sol}/variable_mapping.txt")

    print(f"Number of hard clauses: {len(hard_clauses)}")
    print(f"Number of soft clauses: {len(soft_clauses)}")
    print(f"Total number of variables: {counter - 1}")

    print_variable_counts()

    # Export CNF in tt-open-wbo-inc format
    export_cnf_custom_format(
        filename=f"{args.sol}/formular.wcnf", hard_clauses=hard_clauses, soft_clauses=soft_clauses)
    # Run tt-open-wbo-inc
    solution = run_tt_open_wbo_inc(
        f"{args.sol}/formular.wcnf", args.timeout, f"{args.sol}/log.txt")

    if solution:
        # solution_vars_set = set(solution)
        # debug_s1_penalty(solution_vars_set, N, D, S,
        #                  SK, weekdays, nurse_skills)
        # debug_s7_penalty(solution_vars_set, N, W, nurse_contracts, contracts)
        # debug_s6_penalty(solution_vars_set, N, D, nurse_contracts, contracts)
        save_solutions(args, solution, nurse_name_to_index, weekdays, scenario)
    else:
        print("No solutions.")


def save_solutions(args, solution, nurse_name_to_index, weekdays, scenario):
    """
    Save the solution for each week and validate it.
    """
    scenario_id = scenario['id']
    solution_files = []

    for week_index in range(0, len(weekdays)):
        start_day = week_index * 7
        end_day = (week_index + 1) * 7
        assignments = decode_solution(
            solution, nurse_name_to_index, start_day, end_day)

        solution_file = os.path.join(args.sol, f"sol-week{week_index}.json")
        solution_files.append(solution_file)

        save_solution(assignments, scenario_id, week_index, solution_file)
        print(f"Solution for week {week_index} saved in {solution_file}")

    # Run the validator
    solution_files_str = " ".join(solution_files)
    validator_command = f"java -jar validator.jar --sce {args.sce} --his {args.his} --weeks {' '.join(args.weeks)} --sols {solution_files_str}"
    print(f"Validator command: {validator_command}")
    subprocess.run(validator_command, shell=True)


if __name__ == "__main__":
    # Parse arguments
    args = parse_arguments()

    # Load data
    scenario, history, weekdays, N, D, S, SK, W, nurse_skills, forbidden_shifts, nurse_name_to_index, nurse_contracts, contracts, nurse_history, shift_types = load_data(
        args.sce, args.his, args.weeks)

    # Generate hard and soft clauses
    hard_clauses = generate_hard_clauses(
        N, D, S, SK, weekdays, nurse_skills, forbidden_shifts, nurse_history)
    soft_clauses = generate_soft_clauses(N, D, S, SK, W, weekdays, nurse_skills,
                                         nurse_name_to_index, nurse_contracts, contracts, nurse_history, shift_types)

    # Map variables
    map_to_x_variables()

    # Export and solve
    export_and_solve(args, hard_clauses, soft_clauses,
                     nurse_name_to_index, weekdays, scenario,
                     N, D, S, SK, W, nurse_skills, nurse_contracts, contracts)
