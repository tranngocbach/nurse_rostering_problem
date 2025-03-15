import subprocess
import os

# Định nghĩa đường dẫn file chứa các lệnh
input_file = "run_instances.sh"  # Đường dẫn file shell script
output_folder = "output_for_binomial"
# output_folder = r"D:\NRP\SC_Encoding\output_for_Binomial"

# Đảm bảo thư mục output tồn tại
os.makedirs(output_folder, exist_ok=True)

# Đọc file đầu vào
with open(input_file, "r", encoding="utf-8") as file:
    lines = file.readlines()

i = 0
while i < len(lines):
    name = lines[i].strip()  # Lấy tên file từ dòng đầu tiên
    i += 1  # Chuyển sang dòng lệnh
    if i >= len(lines):
        break

    command = lines[i].strip()  # Lấy lệnh Python
    i += 2  # Chuyển sang nhóm lệnh tiếp theo

    # Đảm bảo tên file hợp lệ (loại bỏ ký tự không hợp lệ)
    safe_name = name.replace(" ", "_").replace(
        ":", "").replace('"', "").replace("'", "")

    # Tạo đường dẫn file đầu ra
    output_file = os.path.join(output_folder, f"{safe_name}.txt")

    print(f"Đang chạy: {command}")

    # Thực thi lệnh và ghi kết quả vào file
    try:
        result = subprocess.run(command, shell=True,
                                capture_output=True, text=True)
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(result.stdout)  # Ghi output của chương trình
            f.write("\n--- ERROR OUTPUT ---\n")
            f.write(result.stderr)  # Ghi lỗi (nếu có)
    except Exception as e:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(f"Lỗi khi chạy lệnh: {e}")

print("Hoàn thành!")
