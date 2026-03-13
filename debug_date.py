import subprocess
import os
import time

# 테스트용 파일 생성
test_file = "c:/Users/user/.gemini/antigravity/scratch/lastdate_change/test_date_fix.txt"
with open(test_file, "w") as f:
    f.write("test")

target_date = "2025-01-25 13:30:48"
# -LiteralPath를 사용하고 경로를 더 안전하게 쿼트함
ps_command = f'$item = Get-Item -LiteralPath "{test_file}"; $item.LastWriteTime = [DateTime]"{target_date}"'

print(f"Executing: {ps_command}")

try:
    result = subprocess.run(
        ["powershell", "-Command", ps_command],
        capture_output=True,
        text=True
    )
    print(f"Return Code: {result.returncode}")
    print(f"Stdout: {result.stdout}")
    print(f"Stderr: {result.stderr}")
    
    if result.returncode == 0:
        new_time = os.path.getmtime(test_file)
        import datetime
        readable = datetime.datetime.fromtimestamp(new_time).strftime('%Y-%m-%d %H:%M:%S')
        print(f"Verification: Changed time is {readable}")
    else:
        print("Failed to change date.")
except Exception as e:
    print(f"Error: {str(e)}")
