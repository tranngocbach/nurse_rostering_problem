from itertools import permutations
import subprocess
import os
from math import ceil
import json
import argparse
from itertools import combinations
from pypblib import pblib
from pypblib.pblib import PBConfig, Pb2cnf
from pysat.formula import WCNF
from pysat.examples.rc2 import RC2, RC2Stratified
import concurrent.futures
from optilog.encoders.pb import Encoder

variable_dict = {}
reverse_variable_dict = {}
counter = 1
max_var_cmin = 0
hard_clauses = []


def get_variable(name):
    global counter
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


def constraint_H1(N, D, S, nurse_skills):
    clauses = []
    for n in range(N):
        for d in range(D):
            shifts = [get_variable(f"o_{n}_{d}_{s}")
                      for s in S]

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
                    # for sk1 in nurse_skills.get(n, []):
                    #     for sk2 in nurse_skills.get(n, []):
                    #         var1 = get_variable(f"x_{n}_{d}_{s1}_{sk1}")
                    #         var2 = get_variable(f"x_{n}_{d+1}_{s2}_{sk2}")
                    #         clauses.append(f"-{var1} -{var2} 0")
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
                            # for sk in nurse_skills.get(nurse_id, []):
                            #     var2 = get_variable(
                            #         f"x_{nurse_id}_0_{s2}_{sk}")
                            #     hard_clauses.append(f"-{var2} 0")
                            var2 = get_variable(
                                f"o_{nurse_id}_0_{s2}")
                            hard_clauses.append(f"-{var2} 0")

    return clauses


def constraint_H2(N, D, S, SK, weekdays, nurse_skills):
    hard_clauses = []
    config = PBConfig()
    config.set_PB_Encoder(pblib.PB_BDD)
    pb2 = Pb2cnf(config)

    for d in range(D):
        for s in S:
            for sk in SK:
                Cmin = get_Cmin(weekdays, d, s, sk)
                Copt = get_Copt(weekdays, d, s, sk)
                nurses = [get_variable(f"x_{n}_{d}_{s}_{sk}") for n in range(
                    N) if sk in nurse_skills.get(n, [])]

                # Ensure at least Cmin nurses are assigned (hard constraint)
                # if Copt - Cmin <= 2:
                #     Cmin = Copt
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


def constraint_optilog_H2(N, D, S, SK, weekdays, nurse_skills):
    hard_clauses = []

    for d in range(D):
        for s in S:
            for sk in SK:
                Cmin = get_Cmin(weekdays, d, s, sk)
                Copt = get_Copt(weekdays, d, s, sk)
                nurses = [get_variable(f"x_{n}_{d}_{s}_{sk}") for n in range(
                    N) if sk in nurse_skills.get(n, [])]

                # Ensure at least Cmin nurses are assigned (hard constraint)
                if Cmin > 0 and len(nurses) >= Cmin:
                    global max_var_cmin

                    max_var_cmin, formula = Encoder.at_least_k(
                        nurses, Cmin, max_var=len(variable_dict))
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
    config.set_PB_Encoder(pblib.PB_BEST)  # PB_BEST thường tự chọn encoder tốt
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
    soft_clauses = []
    config = PBConfig()
    config.set_PB_Encoder(pblib.PB_BEST)
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

                    global counter
                    counter = max_var_copt + 1
    return soft_clauses


def constraint_optilog_S1(N, D, S, SK, weekdays, nurse_skills, penalty_weight):
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
                        combined_vars, Copt, max_var=current_top_var)

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
        # if CW_min > 1:  # Chỉ cần mã hóa nếu min > 1
        #     for d in range(horizon_length):
        #         e_today = get_variable(f"e_{nurse_id}_{d}")

        #         # --- Định nghĩa biến start_work_n_d ---
        #         start_work_var = get_variable(f"start_work_{nurse_id}_{d}")

        #         # Điều kiện 1: start_work_n_d => e_n_d (Nếu bắt đầu làm việc thì phải làm việc hôm nay)
        #         # Tương đương: -start_work_n_d V e_n_d
        #         soft_clauses.append(
        #             (penalty_weight, f"-{start_work_var} {e_today} 0"))

        #         if d == 0:
        #             # Ngày đầu tiên: Bắt đầu làm nếu làm hôm nay VÀ không làm liên tục từ history
        #             if cons_working_days == 0:
        #                 # e_n_0 => start_work_n_0 (Nếu làm ngày 0 và không làm từ history => bắt đầu)
        #                 # Tương đương: -e_n_0 V start_work_n_0
        #                 soft_clauses.append(
        #                     (penalty_weight, f"-{e_today} {start_work_var} 0"))
        #             else:
        #                 # Nếu làm việc từ history thì không thể bắt đầu ngày 0
        #                 # start_work_n_0 là False
        #                 soft_clauses.append(
        #                     (penalty_weight, f"-{start_work_var} 0"))
        #         else:
        #             # Các ngày khác: Bắt đầu làm nếu làm hôm nay VÀ không làm hôm qua
        #             e_yesterday = get_variable(f"e_{nurse_id}_{d - 1}")
        #             # (e_n_d AND NOT e_n_{d-1}) => start_work_n_d
        #             # Tương đương: -(e_n_d AND NOT e_n_{d-1}) V start_work_n_d
        #             # Tương đương: (NOT e_n_d) V e_n_{d-1} V start_work_n_d
        #             soft_clauses.append(
        #                 (penalty_weight, f"-{e_today} {e_yesterday} {start_work_var} 0"))

        #             # Chiều ngược lại: start_work_n_d => NOT e_n_{d-1} (Nếu bắt đầu thì chắc chắn không làm hôm qua)
        #             # Tương đương: -start_work_n_d V -e_n_{d-1}
        #             soft_clauses.append(
        #                 (penalty_weight, f"-{start_work_var} -{e_yesterday} 0"))

        #         # --- Ràng buộc implication: start_work_n_d => làm việc trong CW_min ngày tới ---
        #         for j in range(CW_min):
        #             day_idx = d + j
        #             if day_idx < horizon_length:
        #                 e_future = get_variable(f"e_{nurse_id}_{day_idx}")
        #                 # start_work_n_d => e_n_{d+j}
        #                 # Tương đương: -start_work_n_d V e_n_{d+j}
        #                 soft_clauses.append(
        #                     (penalty_weight, f"-{start_work_var} {e_future} 0"))
        #             # else: # Nếu d+j vượt quá horizon, không cần làm gì thêm
        #                 # Tuy nhiên, cần xử lý trường hợp một khối công việc BẮT ĐẦU gần cuối
        #                 # mà không đủ ngày để hoàn thành CW_min. Ràng buộc này sẽ tự động
        #                 # ngăn chặn việc start_work_n_d là True trong trường hợp đó nếu các e_future không thể True.

        #     # --- Xử lý History cho CW_min ---
        #     # Nếu y tá đã làm việc `cons_working_days` ngày liên tục từ trước
        #     # và `cons_working_days < CW_min` và `cons_working_days > 0`,
        #     # thì họ phải làm việc thêm `CW_min - cons_working_days` ngày nữa.
        #     if 0 < cons_working_days < CW_min:
        #         needed_more_days = CW_min - cons_working_days
        #         # Đảm bảo không vượt quá horizon
        #         for i in range(min(needed_more_days, horizon_length)):
        #             e_day_i = get_variable(f"e_{nurse_id}_{i}")
        #             # Phải làm việc vào ngày i: e_n_i là True
        #             soft_clauses.append(
        #                 (penalty_weight, f"{e_day_i} 0"))

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
            # if CS_min > 1:  # Chỉ cần mã hóa nếu min > 1
            #     for d in range(horizon_length):
            #         o_today = get_variable(f"o_{nurse_id}_{d}_{shift_id}")

            #         # --- Định nghĩa biến start_shift_n_d_s ---
            #         start_shift_var = get_variable(
            #             f"start_shift_{nurse_id}_{d}_{shift_id}")

            #         # Điều kiện 1: start_shift => o_today
            #         soft_clauses.append(
            #             (penalty_weight, f"-{start_shift_var} {o_today} 0"))

            #         if d == 0:
            #             # Ngày đầu tiên: Bắt đầu làm ca s nếu làm hôm nay VÀ không làm ca s từ history
            #             if cons_working_shifts == 0:
            #                 # o_today => start_shift
            #                 soft_clauses.append(
            #                     (penalty_weight, f"-{o_today} {start_shift_var} 0"))
            #             else:
            #                 # Nếu làm ca s từ history thì không thể bắt đầu ngày 0
            #                 soft_clauses.append(
            #                     (penalty_weight, f"-{start_shift_var} 0"))
            #         else:
            #             # Các ngày khác: Bắt đầu làm ca s nếu làm hôm nay VÀ không làm hôm qua
            #             o_yesterday = get_variable(
            #                 f"o_{nurse_id}_{d - 1}_{shift_id}")
            #             # (o_today AND NOT o_yesterday) => start_shift
            #             soft_clauses.append(
            #                 (penalty_weight, f"-{o_today} {o_yesterday} {start_shift_var} 0"))
            #             # start_shift => NOT o_yesterday
            #             soft_clauses.append(
            #                 (penalty_weight, f"-{start_shift_var} -{o_yesterday} 0"))

            #         # --- Ràng buộc implication: start_shift => làm ca s trong CS_min ngày tới ---
            #         for j in range(CS_min):
            #             day_idx = d + j
            #             if day_idx < horizon_length:
            #                 o_future = get_variable(
            #                     f"o_{nurse_id}_{day_idx}_{shift_id}")
            #                 # start_shift => o_future
            #                 soft_clauses.append(
            #                     (penalty_weight, f"-{start_shift_var} {o_future} 0"))

            #     # --- Xử lý History cho CS_min ---
            #     # Nếu y tá đã làm ca s `cons_working_shifts` ngày liên tục
            #     # và `cons_working_shifts < CS_min` và > 0,
            #     # thì họ phải làm ca s thêm `CS_min - cons_working_shifts` ngày nữa.
            #     if 0 < cons_working_shifts < CS_min:
            #         needed_more_shifts = CS_min - cons_working_shifts
            #         for i in range(min(needed_more_shifts, horizon_length)):
            #             o_day_i = get_variable(f"o_{nurse_id}_{i}_{shift_id}")
            #             # Phải làm ca s vào ngày i
            #             soft_clauses.append(
            #                 (penalty_weight, f"{o_day_i} 0"))

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
        # if CF_min > 1:  # Chỉ cần mã hóa nếu min > 1
        #     for d in range(horizon_length):
        #         e_today = get_variable(f"e_{nurse_id}_{d}")
        #         not_e_today = f"-{e_today}"  # Nghỉ hôm nay

        #         # --- Định nghĩa biến start_off_n_d ---
        #         start_off_var = get_variable(f"start_off_{nurse_id}_{d}")

        #         # Điều kiện 1: start_off => NOT e_today
        #         soft_clauses.append(
        #             (penalty_weight, f"-{start_off_var} {not_e_today} 0"))

        #         if d == 0:
        #             # Ngày đầu tiên: Bắt đầu nghỉ nếu nghỉ hôm nay VÀ không nghỉ liên tục từ history
        #             if cons_working_days_off == 0:
        #                 # NOT e_today => start_off
        #                 soft_clauses.append(
        #                     (penalty_weight, f"{e_today} {start_off_var} 0"))  # e_today V start_off
        #             else:
        #                 # Nếu nghỉ từ history thì không thể bắt đầu nghỉ ngày 0
        #                 soft_clauses.append(
        #                     (penalty_weight, f"-{start_off_var} 0"))
        #         else:
        #             # Các ngày khác: Bắt đầu nghỉ nếu nghỉ hôm nay VÀ làm việc hôm qua
        #             e_yesterday = get_variable(f"e_{nurse_id}_{d - 1}")
        #             # (NOT e_today AND e_yesterday) => start_off
        #             # e_today V -e_yesterday V start_off
        #             soft_clauses.append(
        #                 (penalty_weight, f"{e_today} -{e_yesterday} {start_off_var} 0"))
        #             # start_off => e_yesterday
        #             soft_clauses.append(
        #                 (penalty_weight, f"-{start_off_var} {e_yesterday} 0"))

        #         # --- Ràng buộc implication: start_off => nghỉ trong CF_min ngày tới ---
        #         for j in range(CF_min):
        #             day_idx = d + j
        #             if day_idx < horizon_length:
        #                 e_future = get_variable(f"e_{nurse_id}_{day_idx}")
        #                 not_e_future = f"-{e_future}"
        #                 # start_off => NOT e_future
        #                 soft_clauses.append(
        #                     (penalty_weight, f"-{start_off_var} {not_e_future} 0"))

        #     # --- Xử lý History cho CF_min ---
        #     if 0 < cons_working_days_off < CF_min:
        #         needed_more_off_days = CF_min - cons_working_days_off
        #         for i in range(min(needed_more_off_days, horizon_length)):
        #             e_day_i = get_variable(f"e_{nurse_id}_{i}")
        #             # Phải nghỉ vào ngày i
        #             soft_clauses.append(
        #                 (penalty_weight, f"-{e_day_i} 0"))

    return soft_clauses


def constraint_total_weekends(N, W, nurse_contracts, contracts, penalty_weight):
    """
    Tạo ràng buộc mềm S7 (max working weekends) dùng pypblib cho phần cứng.

    Thêm các mệnh đề CỨNG vào global `hard_clauses`.
    Trả về danh sách các mệnh đề MỀM.
    """
    global counter, hard_clauses, variable_dict, reverse_variable_dict

    soft_clauses_for_S7 = []

    # Khởi tạo pypblib
    config = PBConfig()
    config.set_PB_Encoder(pblib.PB_BEST)
    pb2 = Pb2cnf(config)

    for n in range(N):
        contract_id = nurse_contracts[n]
        contract = contracts[contract_id]
        # Dùng W+1 làm mặc định nếu không có trong hợp đồng
        max_weekends = contract.get('maximumNumberOfWorkingWeekends', W + 1)

        # Chỉ mã hóa nếu có giới hạn thực sự (max_weekends < W)
        if 0 <= max_weekends < W:
            # Lấy các biến q_n_w (đã được định nghĩa ở đâu đó dựa trên e_n_sat/sun)
            weekend_vars_q = [get_variable(f"q_{n}_{w}") for w in range(W)]
            num_weekend_vars = len(weekend_vars_q)

            if not weekend_vars_q:  # Bỏ qua nếu không có biến cuối tuần
                continue

            # --- Mã hóa sum(q_n_w) <= max_weekends ---
            # Biến đổi: sum(-q_n_w) >= num_weekend_vars - max_weekends
            target_atleast_k_prime = num_weekend_vars - max_weekends

            # 1. Tạo biến phạt cho việc *vượt quá* max_weekends
            num_penalty = target_atleast_k_prime
            penalty_vars_excess = []
            if num_penalty > 0:
                for j in range(num_penalty):
                    p_var = get_variable(f"penalty_s7_excess_pblib_{n}_{j}")
                    penalty_vars_excess.append(p_var)

            # 2. Tạo biến phụ trợ phủ định (-q_n_w) và mệnh đề cứng định nghĩa chúng
            negated_q_vars_helper = []
            for w_idx, q_var in enumerate(weekend_vars_q):
                # Cần tên gốc của q_var để tạo tên biến phủ định duy nhất
                if q_var in reverse_variable_dict:  # Kiểm tra xem q_var có tồn tại không
                    q_var_name = reverse_variable_dict[q_var]
                    # Thêm _s7 để tránh trùng
                    neg_q_helper_name = f"neg_{q_var_name}_s7"
                    neg_q_helper_var = get_variable(neg_q_helper_name)
                    negated_q_vars_helper.append(neg_q_helper_var)
                    # Định nghĩa cứng: neg_q <=> NOT q
                    hard_clauses.append(f"-{neg_q_helper_var} -{q_var} 0")
                    hard_clauses.append(f"{neg_q_helper_var} {q_var} 0")
                else:
                    # Xử lý trường hợp q_var không tìm thấy (có thể là lỗi logic trước đó)
                    print(
                        f"CẢNH BÁO (S7 pypblib): Không tìm thấy tên cho biến ID {q_var}")
                    # Có thể bỏ qua biến này hoặc dừng chương trình tùy logic của bạn
                    continue

            # 3. Ràng buộc CỨNG: sum(neg_q_helpers) + sum(penalty_vars_excess) >= target_atleast_k_prime
            combined_vars_for_atleast = negated_q_vars_helper + penalty_vars_excess

            # Đảm bảo target_atleast_k_prime >= 0 và có biến để mã hóa
            if target_atleast_k_prime >= 0 and combined_vars_for_atleast:
                formula_hard = []
                current_top_var = counter - 1
                top_var_pblib = pb2.encode_at_least_k(
                    combined_vars_for_atleast,
                    target_atleast_k_prime,
                    formula_hard,
                    current_top_var + 1
                )
                # Thêm mệnh đề cứng
                for clause in formula_hard:
                    hard_clauses.append(" ".join(map(str, clause)) + " 0")
                # Cập nhật biến phụ trợ
                for var_idx in range(current_top_var + 1, top_var_pblib + 1):
                    aux_name = f"aux_s7_pblib_{n}_{var_idx}"
                    if var_idx not in reverse_variable_dict:
                        variable_dict[aux_name] = var_idx
                        reverse_variable_dict[var_idx] = aux_name
                counter = max(counter, top_var_pblib + 1)

            # 4. Ràng buộc MỀM cho biến phạt
            for p_var in penalty_vars_excess:
                soft_clauses_for_S7.append((penalty_weight, f"-{p_var} 0"))

    return soft_clauses_for_S7


def constraint_optilog_total_weekends(N, W, nurse_contracts, contracts, penalty_weight):
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
                    max_var=current_top_var
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


def constraint_total_assignments(N, D, nurse_contracts, contracts, penalty_weight):
    """
    Tạo ràng buộc mềm S6 (min/max total assignments) dùng pypblib cho phần cứng.

    Thêm các mệnh đề CỨNG vào global `hard_clauses`.
    Trả về danh sách các mệnh đề MỀM.
    """
    global counter, hard_clauses, variable_dict, reverse_variable_dict

    soft_clauses_for_S6 = []

    # Khởi tạo pypblib (chỉ cần một lần nếu dùng cùng config)
    config = PBConfig()
    config.set_PB_Encoder(pblib.PB_BEST)
    pb2 = Pb2cnf(config)

    for n in range(N):
        contract_id = nurse_contracts[n]
        contract = contracts[contract_id]
        # Sử dụng D+1 và -1 làm giá trị mặc định nếu không có trong hợp đồng
        max_assign = contract.get('maximumNumberOfAssignments', D + 1)
        # Dùng -1 để dễ kiểm tra
        min_assign = contract.get('minimumNumberOfAssignments', -1)

        # Lấy các biến e_n_d cho y tá n
        assignment_vars_e = [get_variable(f"e_{n}_{d}") for d in range(D)]
        num_assign_vars = len(assignment_vars_e)

        if not assignment_vars_e:  # Bỏ qua nếu y tá không có ngày nào
            continue

        # --- Phần Max assignments: sum(e_n_d) <= max_assign ---
        # Chỉ mã hóa nếu có giới hạn thực sự (max_assign < D)
        if 0 <= max_assign < num_assign_vars:
            target_atleast_k_prime_max = num_assign_vars - \
                max_assign  # K' cho phép biến đổi at-least-k

            # 1. Tạo biến phạt vượt quá max_assign
            num_penalty_max = target_atleast_k_prime_max
            penalty_vars_max = []
            if num_penalty_max > 0:
                for j in range(num_penalty_max):
                    p_var = get_variable(f"penalty_s6_max_pblib_{n}_{j}")
                    penalty_vars_max.append(p_var)

            # 2. Tạo biến phụ trợ phủ định (-e_n_d) và mệnh đề cứng định nghĩa chúng
            negated_e_vars_helper = []
            for d_idx, e_var in enumerate(assignment_vars_e):
                e_var_name = reverse_variable_dict[e_var]
                # Thêm _s6 để tránh trùng tên
                neg_e_helper_name = f"neg_{e_var_name}_s6"
                neg_e_helper_var = get_variable(neg_e_helper_name)
                negated_e_vars_helper.append(neg_e_helper_var)
                # Định nghĩa cứng: neg_e <=> NOT e
                hard_clauses.append(f"-{neg_e_helper_var} -{e_var} 0")
                hard_clauses.append(f"{neg_e_helper_var} {e_var} 0")

            # 3. Ràng buộc CỨNG: sum(neg_e_helpers) + sum(penalty_vars_max) >= target_atleast_k_prime_max
            combined_vars_max = negated_e_vars_helper + penalty_vars_max
            if target_atleast_k_prime_max >= 0 and combined_vars_max:
                formula_max_hard = []
                current_top_var = counter - 1
                top_var_pblib_max = pb2.encode_at_least_k(
                    combined_vars_max,
                    target_atleast_k_prime_max,
                    formula_max_hard,
                    current_top_var + 1
                )
                # Thêm mệnh đề cứng
                for clause in formula_max_hard:
                    hard_clauses.append(" ".join(map(str, clause)) + " 0")
                # Cập nhật biến phụ trợ
                for var_idx in range(current_top_var + 1, top_var_pblib_max + 1):
                    aux_name = f"aux_s6_max_pblib_{n}_{var_idx}"
                    if var_idx not in reverse_variable_dict:
                        variable_dict[aux_name] = var_idx
                        reverse_variable_dict[var_idx] = aux_name
                counter = max(counter, top_var_pblib_max + 1)

            # 4. Ràng buộc MỀM cho biến phạt max
            for p_var in penalty_vars_max:
                soft_clauses_for_S6.append((penalty_weight, f"-{p_var} 0"))

        # --- Phần Min assignments: sum(e_n_d) >= min_assign ---
        # Chỉ mã hóa nếu có giới hạn thực sự (min_assign > 0)
        if min_assign > 0:
            max_shortfall_min = min_assign

            # 1. Tạo biến phạt thiếu hụt min_assign
            penalty_vars_min = []
            if max_shortfall_min > 0:
                for j in range(max_shortfall_min):
                    p_var = get_variable(f"penalty_s6_min_pblib_{n}_{j}")
                    penalty_vars_min.append(p_var)

            # 2. Ràng buộc CỨNG: sum(e_n_d) + sum(penalty_vars_min) >= min_assign
            combined_vars_min = assignment_vars_e + penalty_vars_min
            if combined_vars_min:  # Chỉ mã hóa nếu có biến
                formula_min_hard = []
                current_top_var = counter - 1
                top_var_pblib_min = pb2.encode_at_least_k(
                    combined_vars_min,
                    min_assign,
                    formula_min_hard,
                    current_top_var + 1
                )
                # Thêm mệnh đề cứng
                for clause in formula_min_hard:
                    hard_clauses.append(" ".join(map(str, clause)) + " 0")
                # Cập nhật biến phụ trợ
                for var_idx in range(current_top_var + 1, top_var_pblib_min + 1):
                    aux_name = f"aux_s6_min_pblib_{n}_{var_idx}"
                    if var_idx not in reverse_variable_dict:
                        variable_dict[aux_name] = var_idx
                        reverse_variable_dict[var_idx] = aux_name
                counter = max(counter, top_var_pblib_min + 1)

            # 3. Ràng buộc MỀM cho biến phạt min
            for p_var in penalty_vars_min:
                soft_clauses_for_S6.append((penalty_weight, f"-{p_var} 0"))

    return soft_clauses_for_S6


def constraint_optilog_total_assignments(N, D, nurse_contracts, contracts, penalty_weight):
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
                    max_var=current_top_var
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
                        max_var=current_top_var
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

def run_open_wbo(wcnf_path, timeout, output_file):
    try:
        cmd = ["./open-wbo", wcnf_path, f"-cpu-lim={timeout}"]
        result = subprocess.run(cmd, capture_output=True, text=True)

        with open(output_file, 'w') as f:
            f.write(result.stdout)
            if result.stderr:
                f.write(result.stderr)

        output = result.stdout
        with open("log.txt", 'w') as f:
            f.write(output)
        if "s SATISFIABLE" in output or "s OPTIMUM" in output:
            solution = [reverse_variable_dict[abs(int(lit))] for line in output.splitlines() if line.startswith('v')
                        for lit in line.split()[1:] if int(lit) > 0]
            return solution
        elif "s UNSATISFIABLE" in output:
            print("The problem is unsatisfiable.")
            return None
        else:
            print("No valid solution found in the output.")
            return None

    except Exception as e:
        print(f"An error occurred while running Open-WBO: {e}")
        return None


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
    try:
        cmd = ["timeout", str(timeout),
               "./tt-open-wbo-inc-Glucose4_1_static", wcnf_path]
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Nurse Rostering Problem Solver")
    parser.add_argument('--sce', required=True, help='Scenario File')
    parser.add_argument('--his', required=True, help='Initial History File')
    parser.add_argument('--weeks', required=True,
                        nargs='+', help='Weeks Data Files')
    parser.add_argument('--sol', required=True, help='Solution Folder')
    parser.add_argument('--timeout', type=float, help='Timeout in Seconds')

    args = parser.parse_args()

    scenario, history, weekdays, N, D, S, SK, W, nurse_skills, forbidden_shifts, nurse_name_to_index, nurse_contracts, contracts, nurse_history, shift_types = load_data(
        args.sce, args.his, args.weeks)

    hard_clauses_H1 = constraint_H1(N, D, S, nurse_skills)
    hard_clauses += hard_clauses_H1
    print(f"Number of clauses for H1: {len(hard_clauses_H1)}")

    hard_clauses += constraint_H3(N, D, S, SK,
                                  nurse_skills, forbidden_shifts, nurse_history)

    hard_clauses_aux = constraint_aux(N, D, S, nurse_skills)
    hard_clauses += hard_clauses_aux
    print(f"Number of clauses for aux: {len(hard_clauses_aux)}")

    hard_clauses_H2 = constraint_H2(N, D, S, SK, weekdays, nurse_skills)
    hard_clauses += hard_clauses_H2
    print(f"Number of clauses for H2: {len(hard_clauses_H2)}")
    # optilog_H2_clauses = constraint_optilog_H2(
    #     N, D, S, SK, weekdays, nurse_skills)
    # hard_clauses += optilog_H2_clauses
    # print(f"Number of clauses for optilog_H2: {len(optilog_H2_clauses)}")

    soft_clauses = []

    # soft_clauses_S1 = constraint_S1(
    #     N, D, S, SK, weekdays, nurse_skills, penalty_weight=30)
    # soft_clauses += soft_clauses_S1
    # print(f"Number of soft clauses for S1: {len(soft_clauses_S1)}")

    # soft_clauses_S1 = constraint_optilog_S1(
    #     N, D, S, SK, weekdays, nurse_skills, penalty_weight=30)
    # soft_clauses += soft_clauses_S1
    # print(f"Number of soft clauses for optilog_S1: {len(soft_clauses_S1)}")

    soft_clauses_S1 = constraint_S1_pypblib(
        N, D, S, SK, weekdays, nurse_skills, penalty_weight=30)
    soft_clauses += soft_clauses_S1
    print(f"Number of soft clauses for S1: {len(soft_clauses_S1)}")

    soft_clauses_S5 = constraint_S5(N, D, nurse_contracts,
                                    contracts, penalty_weight=30)
    soft_clauses += soft_clauses_S5
    print(f"Number of soft clauses for S5: {len(soft_clauses_S5)}")

    soft_clauses_S4_SOR = constraint_S4_SOR(
        weekdays, nurse_name_to_index, penalty_weight=10)
    soft_clauses += soft_clauses_S4_SOR
    print(f"Number of soft clauses for S4_SOR: {len(soft_clauses_S4_SOR)}")

    soft_clauses_S2_cons_work_day = constraint_S2_cons_work_day(
        weekdays, nurse_history, nurse_name_to_index, nurse_contracts, contracts, penalty_weight=30)
    soft_clauses += soft_clauses_S2_cons_work_day
    print(
        f"Number of soft clauses for S2_cons_work_day: {len(soft_clauses_S2_cons_work_day)}")

    soft_clauses_S2_cons_work_shift = constraint_S2_cons_work_shift(
        weekdays, nurse_history, nurse_name_to_index, shift_types, penalty_weight=15)
    soft_clauses += soft_clauses_S2_cons_work_shift
    print(
        f"Number of soft clauses for S2_cons_work_shift: {len(soft_clauses_S2_cons_work_shift)}")

    soft_clauses_S3 = constraint_S3(weekdays, nurse_history, nurse_name_to_index,
                                    nurse_contracts, contracts, penalty_weight=30)
    soft_clauses += soft_clauses_S3
    print(f"Number of soft clauses for S3: {len(soft_clauses_S3)}")

    soft_clauses_total_weekends = constraint_total_weekends(
        N, W, nurse_contracts, contracts, penalty_weight=30)
    soft_clauses += soft_clauses_total_weekends
    print(
        f"Number of soft clauses for total_weekends: {len(soft_clauses_total_weekends)}")

    soft_clauses_total_assignments = constraint_total_assignments(
        N, D, nurse_contracts, contracts, penalty_weight=20)
    soft_clauses += soft_clauses_total_assignments
    print(
        f"Number of soft clauses for total_assignments: {len(soft_clauses_total_assignments)}")

    # soft_clauses_optilog_total_weekends = constraint_optilog_total_weekends(
    #     N, W, nurse_contracts, contracts, penalty_weight=30)
    # soft_clauses += soft_clauses_optilog_total_weekends
    # print(
    #     f"Number of soft clauses for optilog_total_weekends: {len(soft_clauses_optilog_total_weekends)}")

    # soft_clauses_optilog_total_assignments = constraint_optilog_total_assignments(
    #     N, D, nurse_contracts, contracts, penalty_weight=20)
    # soft_clauses += soft_clauses_optilog_total_assignments
    # print(
    #     f"Number of soft clauses for optilog_total_assignments: {len(soft_clauses_optilog_total_assignments)}")

    map_to_x_variables()

    if not os.path.exists(args.sol):
        os.makedirs(args.sol)
    export_variable_mapping(filename=f"{args.sol}/variable_mapping.txt")

    print(f"Number of hard clauses: {len(hard_clauses)}")
    print(f"Number of soft clauses: {len(soft_clauses)}")
    print(f"Total number of variables: {counter - 1}")

    print_variable_counts()

    # export_cnf(filename=f"{args.sol}/formular.wcnf", hard_clauses=hard_clauses,
    #            soft_clauses=soft_clauses, weight_hard=200)

    export_cnf_custom_format(filename=f"{args.sol}/formular.wcnf", hard_clauses=hard_clauses,
                             soft_clauses=soft_clauses)

    # solution = run_open_wbo(
    #     f"{args.sol}/formular.wcnf", args.timeout, f"{args.sol}/log.txt")
    solution = run_tt_open_wbo_inc(
        f"{args.sol}/formular.wcnf", args.timeout, f"{args.sol}/log.txt")
    # process_log_file("log.txt", "sol.txt")
    # sol = read_solution_file("sol.txt")
    # solution = [reverse_variable_dict[abs(var)] for var in sol if var > 0]
    if solution:
        # Extract scenario ID from the scenario file
        scenario_id = scenario['id']

        # List to store solution file names
        solution_files = []

        # Save solutions for each week separately
        for week_index in range(0, len(weekdays)):
            start_day = week_index * 7
            end_day = (week_index + 1) * 7
            assignments = decode_solution(
                solution, nurse_name_to_index, start_day, end_day)

            # Generate solution file name
            solution_file = os.path.join(
                args.sol, f"sol-week{week_index}.json")
            solution_files.append(solution_file)

            save_solution(assignments, scenario_id, week_index, solution_file)

            print(f"Solution for week {week_index} saved in {solution_file}")

        # Generate validator command
        solution_files_str = " ".join(solution_files)
        validator_command = f"java -jar validator.jar --sce {args.sce} --his {args.his} --weeks {' '.join(args.weeks)} --sols {solution_files_str}"
        print(f"Validator command: {validator_command}")

        # Run the validator command
        subprocess.run(validator_command, shell=True)
    else:
        print("No solutions.")
