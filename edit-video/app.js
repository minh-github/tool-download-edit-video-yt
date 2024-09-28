const fs = require('fs')
const path = require('path')
const { exec } = require('child_process')
const xlsx = require('xlsx')
const { SingleBar, Presets } = require('cli-progress');

// Đường dẫn đến thư mục chứa video và thư mục đầu ra
const videoFolder = './video_download' // Thay đổi đường dẫn nếu cần
const outputFolder = './video_out' // Thư mục đầu ra
const musicFolder = './settings/background_music' // Thư mục đầu ra
const backgroundVideoFolder = './settings/background_video' // Thư mục đầu ra

// Tạo thư mục đầu ra nếu chưa tồn tại
const createOutputFolder = () => {
  if (!fs.existsSync(outputFolder)) {
    fs.mkdirSync(outputFolder)
  }
}

// Đọc dữ liệu từ file Excel
const readChoicesFromExcel = (excelFilePath) => {
  const workbook = xlsx.readFile(excelFilePath)
  const sheet = workbook.Sheets[workbook.SheetNames[0]]
  const data = xlsx.utils.sheet_to_json(sheet)

  return data.map(row => ({
    speed: row['Speed'] ? parseFloat(row['Speed']) : null,
    opacity: row['Opacity'] ? parseFloat(row['Opacity']) : null,
    flip: row['flip'],
    audioTone: row['audio tone'] ? parseFloat(row['audio tone']) : null,
    red: row['red'] ? parseInt(row['red'], 10) : null,
    green: row['green'] ? parseInt(row['green'], 10) : null,
    blue: row['blue'] ? parseInt(row['blue'], 10) : null,
    brightness: row['brightness'] ? parseFloat(row['brightness']) : null,
    contrast: row['contrast'] ? parseFloat(row['contrast']) : null, // Thêm contrast
    saturation: row['saturation'] ? parseFloat(row['saturation']) : null, // Thêm saturation
    gamma: row['gamma'] ? parseFloat(row['gamma']) : null, // Thêm gamma
    hue: row['hue'] ? parseFloat(row['hue']) : null, // Thêm hue
    cutAhead: row['cut ahead video'] ? parseFloat(row['cut ahead video']) : null,
    cutEnd: row['cut end video'] ? parseFloat(row['cut end video']) : null,
    mainVolume: row['main volume'] !== null && row['main volume'] !== undefined ? parseFloat(row['main volume']) : 1.0,
    backgroundVolume: row['background volume'] !== null && row['background volume'] !== undefined ? parseFloat(row['background volume']) : 1.0,
    backgroundMusicPath: row['background music path'],
    aspectRatio: row['aspect ratio'] || null,
    direction: row['direction'] || 'horizontal',
    music: row['music'] || 'no',
  }))[0]; // Trả về hàng đầu tiên như các tùy chọn cho tất cả video
}

const createFfmpegCommand = (inputPath, outputPath, options) => {
  let filter = [];
  let cutStart = '';
  let cutEnd = '';
  let backgroundMusic = '';

  // Handle video filters
  if (options.flip) {
    filter.push(options.flip === 'horizontal' ? 'hflip' : 'vflip');
  }

  // Adjust video speed
  if (options.speed) {
    filter.push(`setpts=${1 / options.speed}*PTS`);
  }

  if (options.opacity) {
    filter.push(`format=rgba,colorchannelmixer=aa=${options.opacity}`);
  }

  if (options.contrast) {
    filter.push(`eq=contrast=${options.contrast}`);
  }

  if (options.saturation) {
    filter.push(`eq=saturation=${options.saturation}`);
  }

  if (options.gamma) {
    filter.push(`eq=gamma=${options.gamma}`);
  }

  // Cutting video
  if (options.cutAhead) {
    cutStart = `-ss ${options.cutAhead}`;
  }

  if (options.cutEnd) {
    cutEnd = `-sseof -${options.cutEnd}`;
  }

  // Background music
  if (options.music === 'yes') {
    const musicPath = `${musicFolder}/${options.backgroundMusicPath}`;
    backgroundMusic = `-i "${musicPath}" `;
  }

  const pixelFormat = `-pix_fmt yuv420p`;

  // Set output resolution and bitrate
  const videoBitrate = '-b:v 4M'; // Adjust bitrate as needed

  // Handling filter_complex
  let complexFilter = '';
  const videoFilters = filter.length ? filter.join(',') : 'null';
  
  if (options.music === 'yes') {
    complexFilter = `[0:v]${videoFilters}[v]; [0:a]volume=${options.mainVolume},atempo=${options.speed}[a1]; [1:a]volume=${options.backgroundVolume}[a2]; [a1][a2]amix=inputs=2:duration=shortest[a]`;
  } else {
    complexFilter = `[0:v]${videoFilters}[v]; [0:a]volume=${options.mainVolume},atempo=${options.speed}[a]`;
  }

  // Final ffmpeg command
  // -c:v h264_nvenc -preset slow -rc cqp -qp 18 -b:v 10000k
  return `ffmpeg -y -hide_banner -loglevel error ${cutStart} ${cutEnd} -i "${inputPath}" ${backgroundMusic} -filter_complex "${complexFilter}" -c:v h264_amf -rc cqp -qp_i 10 -qp_p 20 -qp_b 30 -map "[v]" -map "[a]" ${pixelFormat} "${outputPath}"`;
};

// Thực thi lệnh ffmpeg cho từng tệp video
const processVideoFile = async (videoFile, options) => {
  const inputPath = path.join(videoFolder, videoFile).replace(/\\/g, '/')
  const outputPath = path.join(outputFolder, `edited_${path.parse(videoFile).name}.mp4`).replace(/\\/g, '/') // Đảm bảo tệp đầu ra là MP4

  const ffmpegCommand = createFfmpegCommand(inputPath, outputPath, options)  
  return new Promise((resolve, reject) => {
    exec(ffmpegCommand, (error, stdout, stderr) => {
      if (error) {
        console.error(`Lỗi khi xử lý video ${videoFile}:`, stderr)
        return reject(error)
      }
      resolve()
    })
  })
}

// Lấy danh sách các video trong thư mục
const getVideoFiles = () => {
  return new Promise((resolve, reject) => {
    fs.readdir(videoFolder, (err, files) => {
      if (err) {
        reject('Không thể đọc thư mục:', err)
        return
      }

      const videoFiles = files.filter(file => {
        const ext = path.extname(file).toLowerCase()
        return ext === '.mp4' || ext === '.avi' || ext === '.mov'
      })

      if (videoFiles.length === 0) {
        reject('Không có tệp video nào trong thư mục.')
      } else {
        resolve(videoFiles)
      }
    })
  })
}

// Quản lý xử lý video từ Excel
const processVideosFromExcel = async (excelFilePath) => {
  try {
    createOutputFolder();
    const videoFiles = await getVideoFiles();
    const options = readChoicesFromExcel(excelFilePath); // Đọc tùy chọn chỉ một lần

    // Tạo thanh tiến trình
    const progressBar = new SingleBar({
      format: 'Xử lý video [{bar}] {percentage}% | {value}/{total} video',
      barCompleteChar: '\u2588',
      barIncompleteChar: '\u2591',
      hideCursor: true
    }, Presets.shades_classic);

    // Bắt đầu thanh tiến trình
    progressBar.start(videoFiles.length, 0);

    // Lặp qua từng video và áp dụng các tùy chọn
    for (const videoFile of videoFiles) {
      await processVideoFile(videoFile, options);
      progressBar.increment(); // Cập nhật tiến trình sau khi xử lý từng video
    }

    progressBar.stop(); // Dừng thanh tiến trình khi hoàn tất
    console.log(`Done -- ${videoFiles.length} video <3`);
  } catch (error) {
    console.error(error);
  }
};

// Đường dẫn file Excel và bắt đầu xử lý
const excelFilePath = './settings/choices.xlsx' // Thay đổi đường dẫn nếu cần
processVideosFromExcel(excelFilePath)
