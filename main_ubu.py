import subprocess
import os

# Định nghĩa đường dẫn file shell script
sh_file = "run_instances.sh"  # Đường dẫn file shell script
output_folder = "output_for_binomial"  # Thư mục lưu kết quả

# Đảm bảo thư mục output tồn tại
os.makedirs(output_folder, exist_ok=True)

# Đọc và thực thi file shell script, lấy tên scenario từ echo
try:
    result = subprocess.run(
        f"bash {sh_file}", shell=True, capture_output=True, text=True)

    # Tìm tên scenario từ output của bash (từ dòng echo "Running scenario: ...")
    scenario_name = None
    for line in result.stdout.splitlines():
        if line.startswith("Running scenario:"):
            scenario_name = line.split(":")[1].strip()
            break

    # Nếu tìm thấy tên scenario, tạo file với tên đó
    if scenario_name:
        output_file = os.path.join(output_folder, f"{scenario_name}.txt")
        print(f"Đang lưu kết quả vào: {output_file}")

        # Ghi kết quả đầu ra vào file
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(result.stdout)  # Ghi output của chương trình
            f.write("\n--- ERROR OUTPUT ---\n")
            f.write(result.stderr)  # Ghi lỗi (nếu có)
    else:
        print("Không tìm thấy tên scenario trong output")

except Exception as e:
    print(f"Lỗi khi chạy script: {e}")

print("Hoàn thành!")
