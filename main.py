import sys
import os
import scrapetube
import time
import backoff
from pytube import YouTube
from pytube.innertube import _default_clients
from pytube import cipher
import re
import subprocess
import sys
import io
from tqdm import tqdm  # Import tqdm

# Set the stdout to utf-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Thêm đường dẫn đến thư mục cha của file hiện tại vào sys.path
sys.path.insert(
    0, "/".join(os.path.dirname(os.path.realpath(__file__)).split(os.sep)[:-1])
)

# Nhập lựa chọn công việc
job_choice = input("Lựa chọn công việc của tool: \n'1' Tải xuống và edit \n'2' Tải xuống và không edit \n'3' Chỉ edit (video đã được tải từ trước)\nNhập lựa chọn của bạn: ")

if job_choice == '1':
    job_type = "DownloadAndEdit"
elif job_choice == '2':
    job_type = "DownloadNoEdit"
elif job_choice == '3':
    job_type = "JustEdit"
else:
    job_type = "DownloadAndEdit"

startEdit = False

if job_type == "DownloadAndEdit" or job_type == "DownloadNoEdit":
    # Nhận URL kênh từ bàn phím
    channel_url = input("Nhập URL kênh (ví dụ: https://www.youtube.com/@username): ")
    channel_url = channel_url.strip()
    # Nhận content_type từ bàn phím
    content_choice = input("Nhập 'v' để lấy video hoặc 's' để lấy shorts: ")
    content_type = "shorts" if content_choice.lower() == 's' else "videos"

    # Nhận sort_by từ bàn phím
    sort_choice = input("Thứ tự lấy video: \n'1' phổ biến nhất \n'2' mới nhất \n'3' cũ nhất\nNhập lựa chọn của bạn: ")

    if sort_choice == '1':
        sort_type = "popular"
    elif sort_choice == '2':
        sort_type = "newest"
    elif sort_choice == '3':
        sort_type = "oldest"
    else:
        sort_type = "popular"

    limit_choice = input("Nhập số lượng muốn lấy: ")
    limit_type = int(limit_choice)
    # Lấy videos hoặc shorts từ kênh với giới hạn 10 video
    videos = scrapetube.get_channel(
        channel_url=channel_url,  # URL kênh
        sort_by=sort_type,         # Sắp xếp theo mức độ phổ biến
        content_type=content_type,  # Chỉ định lấy videos hoặc shorts
        limit=limit_type          # Giới hạn video
    )

    # Kiểm tra nếu danh sách videos rỗng
    if not videos:
        print("Không tìm thấy video nào từ kênh này.")
    else:
        # Mở file txt để ghi video ID
        with open("./settings/shorts_ids.txt", "w") as file:
            for video in videos:
                video_id = video["videoId"]
                file.write(video_id + "\n")  # Ghi mỗi videoId vào file

        # print("Danh sách videoId đã được ghi vào file shorts_ids.txt.")

    # Cập nhật phiên bản client
    _default_clients["ANDROID"]["context"]["client"]["clientVersion"] = "19.08.35"
    _default_clients["IOS"]["context"]["client"]["clientVersion"] = "19.08.35"
    _default_clients["ANDROID_EMBED"]["context"]["client"]["clientVersion"] = "19.08.35"
    _default_clients["IOS_EMBED"]["context"]["client"]["clientVersion"] = "19.08.35"
    _default_clients["IOS_MUSIC"]["context"]["client"]["clientVersion"] = "6.41"
    _default_clients["ANDROID_MUSIC"] = _default_clients["ANDROID_CREATOR"]

    # Định nghĩa lớp lỗi
    class RegexMatchError(Exception):
        def __init__(self, caller, pattern):
            self.caller = caller
            self.pattern = pattern
            super().__init__(f"RegexMatchError in {caller}: pattern '{pattern}' not matched.")

    def get_throttling_function_name(js: str) -> str:
        """Extract the name of the function that computes the throttling parameter."""
        function_patterns = [
            r'a\.[a-zA-Z]\s*&&\s*\([a-z]\s*=\s*a\.get\("n"\)\)\s*&&\s*'
            r'\([a-z]\s*=\s*([a-zA-Z0-9$]+)(\[\d+\])?\([a-z]\)',
            r'\([a-z]\s*=\s*([a-zA-Z0-9$]+)(\[\d+\])\([a-z]\)',
        ]
        for pattern in function_patterns:
            regex = re.compile(pattern)
            function_match = regex.search(js)
            if function_match:
                if len(function_match.groups()) == 1:
                    return function_match.group(1)
                idx = function_match.group(2)
                if idx:
                    idx = idx.strip("[]")
                    array = re.search(
                        r'var {nfunc}\s*=\s*(\[.+?\]);'.format(
                            nfunc=re.escape(function_match.group(1))),
                        js
                    )
                    if array:
                        array = array.group(1).strip("[]").split(",")
                        array = [x.strip() for x in array]
                        return array[int(idx)]
        
        raise RegexMatchError(caller="get_throttling_function_name", pattern="multiple")

    cipher.get_throttling_function_name = get_throttling_function_name

    def sanitize_filename(filename):
        """Loại bỏ các ký tự đặc biệt khỏi tên file."""
        return re.sub(r'[\\/*?:"<>|]', "", filename)
    
    @backoff.on_exception(backoff.expo, Exception, max_tries=5)
    def download_video_and_audio(video_id, desired_resolution='1080p'):
        """Tải video và âm thanh từ YouTube, sau đó ghép lại."""
        url = f'https://www.youtube.com/watch?v={video_id}'
        
        video_temp_path = './settings/video_temp'
        video_download_path = './video_download'

        # Tạo thư mục nếu chưa có
        if not os.path.exists(video_temp_path):
            os.makedirs(video_temp_path)
        if not os.path.exists(video_download_path):
            os.makedirs(video_download_path)
        
        try:
            yt = YouTube(url)

            # Tạo tên file cho video
            safe_title = sanitize_filename(yt.title)
            output_file = os.path.join(video_download_path, f"{safe_title}.mp4")
            
            # Kiểm tra xem video đã tồn tại chưa
            if os.path.exists(output_file):
                return

            # Lọc stream video-only với độ phân giải mong muốn
            video_stream = yt.streams.filter(file_extension='mp4', res=desired_resolution, only_video=True).first()
            # Lọc stream audio-only
            audio_stream = yt.streams.filter(only_audio=True).first()

            if video_stream and audio_stream:
                # print(f"Đang tải video: {video_stream.title} với độ phân giải {desired_resolution}")
                video_file = video_stream.download(output_path=video_temp_path, filename='video.mp4')

                # print(f"Đang tải âm thanh: {audio_stream.title}")
                audio_file = audio_stream.download(output_path=video_temp_path, filename='audio.mp4')

                # print("Đang ghép video và âm thanh lại...")
                command = f'ffmpeg -hide_banner -loglevel error -i "{video_file}" -i "{audio_file}" -c:v copy -c:a aac "{output_file}"'
                result = subprocess.run(command, shell=True)

                if result.returncode != 0:
                    print("Có lỗi xảy ra trong quá trình ghép video và âm thanh.")
                # else:
                    # print(f"Video {safe_title} đã được ghép thành công!")

                # Xóa các file video và audio tạm thời
                os.remove(video_file)
                os.remove(audio_file)

            else:
                # if not video_stream:
                    # print(f"Không có stream với độ phân giải {desired_resolution}.")
                # if not audio_stream:
                    # print("Không tìm thấy âm thanh để tải.")
                
                # Thử tải stream có độ phân giải cao nhất có sẵn
                highest_res_stream = yt.streams.filter(file_extension='mp4', only_video=True).order_by('resolution').desc().first()
                
                if highest_res_stream:
                    # print(f"Đang tải: {highest_res_stream.title} với độ phân giải {highest_res_stream.resolution}")
                    video_file = highest_res_stream.download(output_path=video_temp_path, filename='video.mp4')
                    output_file = os.path.join(video_download_path, f"{safe_title}.mp4")

                    # print(f"Đang tải âm thanh: {audio_stream.title}")
                    audio_file = audio_stream.download(output_path=video_temp_path, filename='audio.mp4')

                    # print("Đang ghép video và âm thanh lại...")
                    command = f'ffmpeg -hide_banner -loglevel error -i "{video_file}" -i "{audio_file}" -c:v copy -c:a aac "{output_file}"'


                    result = subprocess.run(command, shell=True)

                    if result.returncode != 0:
                        print("Có lỗi xảy ra trong quá trình ghép video và âm thanh.")
                    # else:
                        # print("Tải video thành công!"
                    # Xóa các file video và audio tạm thời
                    os.remove(video_file)
                    os.remove(audio_file)
                else:
                    print("Không tìm thấy video để tải.")

        except Exception as e:
            print(f'Có lỗi xảy ra với video {video_id}: {e}')
            
    # Đọc danh sách ID từ file
    with open('./settings/shorts_ids.txt', 'r') as file:
        video_ids = [line.strip() for line in file.readlines()]

    # Nhập độ phân giải một lần cho tất cả video
    desired_resolution = '1080p'  # Thay đổi độ phân giải tại đây

    for video_id in tqdm(video_ids, desc="Downloading videos", unit="video"): 
        download_video_and_audio(video_id, desired_resolution)
        time.sleep(5)

if job_type == "JustEdit":
    process = subprocess.Popen(['node', './edit-video/app.js'])
    process.wait()

sys.exit()