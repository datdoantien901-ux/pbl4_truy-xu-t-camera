const express = require('express');
const fs = require('fs');
const path = require('path');

const app = express();
const PORT = 3000;

// 1. Phục vụ các file tĩnh (HTML, CSS) từ thư mục 'public'
app.use(express.static('public'));

// 2. Mở quyền truy cập cho thư mục 'images' do Python tạo ra
app.use('/images', express.static(path.join(__dirname, 'images')));

// 3. Xây dựng API: Trả về tên file ảnh mới nhất
app.get('/api/latest-image', (req, res) => {
    const imagesDir = path.join(__dirname, 'images');
    
    fs.readdir(imagesDir, (err, files) => {
        if (err) {
            return res.status(500).json({ error: 'Không thể đọc thư mục ảnh' });
        }

        // Lọc ra các file .jpg
        const jpgFiles = files.filter(file => file.endsWith('.jpg'));
        
        if (jpgFiles.length === 0) {
            return res.json({ imageUrl: null });
        }

        // Vì Python đang lưu tên file theo Timestamp
        // Nên ta chỉ cần sắp xếp theo bảng chữ cái là sẽ tìm được file mới nhất ở cuối mảng
        jpgFiles.sort();
        const latestFile = jpgFiles[jpgFiles.length - 1];

        // Trả URL của ảnh về cho Client
        res.json({ imageUrl: `/images/${latestFile}` });
    });
});

app.listen(PORT, () => {
    console.log(`✅ Web Server đang chạy tại: http://localhost:${PORT}`);
});