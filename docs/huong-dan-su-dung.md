# Hướng dẫn sử dụng

Tài liệu này viết cho người dùng app, không phải cho người sửa code. Nếu bạn cần
biết hệ thống được lắp thế nào thì đọc README hoặc mở tab Kiến trúc.

## Bắt đầu trong ba phút

1. Mở http://localhost:3000, bạn vào ngay trang **Hôm nay**.
2. Gõ việc cần làm vào ô ở giữa trang, bấm **Thêm**. Xong, task đã được lưu.
3. Bấm **Chi tiết** nếu muốn điền thêm hạn chót, ưu tiên, dự án, tag.

Không cần đăng nhập, không cần cấu hình gì trước. Task nhập ở trang Hôm nay được
tự động xếp vào hôm nay.

## Hai loại "thời gian" và đừng nhầm chúng

Đây là chỗ dễ nhầm nhất, nên nói trước.

| Trường | Trả lời câu hỏi | Dùng khi |
|---|---|---|
| **Ngày dự định làm** | "Hôm nay tôi định làm gì?" | Lập kế hoạch ngày |
| **Hạn chót** | "Việc này phải xong trước khi nào?" | Có deadline thật |

Chúng độc lập nhau. Một task có thể:

- Chỉ có ngày dự định: "hôm nay tôi muốn dọn code", không ai bắt.
- Chỉ có hạn chót: "báo cáo phải gửi thứ Sáu", chưa quyết định làm ngày nào.
- Có cả hai: hạn thứ Sáu, dự định làm thứ Tư.
- Không có gì: việc trong danh sách chờ.

Trang Hôm nay dựa vào **ngày dự định** để biết hôm nay bạn định làm gì, và dựa
vào **hạn chót** để cảnh báo quá hạn. Nếu bạn chỉ điền hạn chót mà không xếp lịch,
task sẽ nằm ở nhóm "Sắp đến hạn trong 7 ngày, chưa xếp lịch" để bạn không quên.

## Các trường khi nhập task

Bấm **Chi tiết** để mở đầy đủ.

| Trường | Ghi chú |
|---|---|
| Tiêu đề | Bắt buộc, tối đa 500 ký tự. Khoảng trắng đầu cuối bị cắt |
| Mô tả | Bối cảnh, tiêu chí hoàn thành, link |
| Dự án | Chọn từ danh sách. Tạo dự án mới ở tab Dự án |
| Trạng thái | Mặc định **Cần làm** |
| Ưu tiên | Mặc định **Trung bình** |
| Ngày dự định làm | Ở trang Hôm nay thì mặc định là hôm nay |
| Hạn chót | Có cả giờ. Lấy múi giờ từ máy bạn |
| Ước lượng | Số phút. Ảnh hưởng tới cách tính tiến độ dự án |
| Tag | Cách nhau bằng dấu phẩy |

Tag được chuẩn hoá tự động: chữ thành chữ thường, khoảng trắng thành dấu gạch
ngang, trùng lặp bị loại. Nhập `Deploy, deploy, Home Lab` sẽ thành
`deploy`, `home-lab`. Tối đa 20 tag một task.

## Năm trạng thái, dùng khi nào

| Trạng thái | Nghĩa |
|---|---|
| **Chờ xử lý** | Đã ghi lại để không quên, chưa cam kết làm |
| **Cần làm** | Đã quyết định sẽ làm |
| **Đang làm** | Đang bắt tay vào. Nên chỉ có vài task ở đây cùng lúc |
| **Bị chặn** | Không làm được vì thứ khác. Nên ghi lý do vào mô tả |
| **Xong** | Hoàn thành |
| **Đã huỷ** | Quyết định không làm nữa. Khác với xoá: vẫn giữ lại để nhớ đã từng cân nhắc |

Hai hành vi tự động đáng biết:

- Chuyển sang **Xong** thì thời điểm hoàn thành được ghi lại, và task xuất hiện ở
  nhóm "Đã xong hôm nay".
- **Mở lại** một task đã xong thì thời điểm hoàn thành bị xoá, để thống kê không
  đếm sai.

## Một ngày làm việc điển hình

**Buổi sáng.** Mở trang Hôm nay. Đọc từ trên xuống:

1. **Quá hạn** — cần xử lý trước, hoặc dời hạn nếu hạn cũ không còn hợp lý.
2. **Đang làm** — việc dở từ hôm qua.
3. **Đã xếp cho hôm nay** — kế hoạch bạn tự đặt.
4. **Sắp đến hạn trong 7 ngày, chưa xếp lịch** — nhìn để chủ động, chưa cần làm.

Bốn ô số ở đầu trang cho biết nhanh: việc đang mở, việc quá hạn, việc xong hôm
nay, và thời gian bạn đã ghi nhận.

**Trong ngày.** Bắt đầu một việc thì đổi trạng thái sang **Đang làm**. Làm xong
thì tích vào ô vuông bên trái, task chuyển sang Xong ngay.

**Muốn thêm việc vào hôm nay?** Mở tab Tất cả task, tìm task đó, bấm **Hôm nay**.
Nút này chỉ hiện với task chưa xếp cho hôm nay.

**Cuối ngày.** Nhóm "Đã xong hôm nay" là bản tổng kết. Nếu trống mà bạn vẫn làm
nhiều thì có thể bạn quên đánh dấu.

## Ghi thời gian đã làm

Mỗi task có nút **+30p** để cộng 30 phút vào thời gian đã làm. Bấm nhiều lần nếu
làm lâu hơn.

Con số này để bạn so với ước lượng ban đầu, biết mình hay đánh giá thấp hay cao.
Tổng thời gian ghi trong ngày hiện ở ô "Thời gian đã ghi" trên trang Hôm nay.

Đây là ghi tay, không phải bấm giờ tự động. Chủ ý như vậy: một cái đồng hồ chạy
nền mà bạn quên tắt sẽ cho số liệu sai còn tệ hơn không có số liệu.

## Dự án

Tab **Dự án** để nhóm task. Mỗi dự án có:

- **Mã** — chữ in hoa, 2 đến 20 ký tự, ví dụ `HOMELAB` hoặc `OPS`. Mã này là thứ
  dùng để đối chiếu khi xuất nhập CSV, nên chọn xong thì đừng đổi.
- **Tên** — mô tả dài hơn.
- **Màu** — để nhận ra nhanh trên thẻ task.

Xoá dự án **không** xoá task của nó. Task chỉ bị gỡ liên kết và trở thành không
thuộc dự án nào.

## Thùng rác

Xoá task là **xoá mềm**. Task vào thùng rác và được giữ **30 ngày**. Trong thời
gian đó nó không xuất hiện ở bất kỳ đâu ngoài tab Thùng rác: không ở agenda,
không trong danh sách, không tính vào thống kê.

Ở tab **Thùng rác**:

- Mỗi task hiện **số ngày còn lại**. Dưới 7 ngày thì số chuyển vàng, dưới 3 ngày
  chuyển đỏ.
- **Phục hồi** đưa task về trạng thái trước khi xoá.
- **Xoá vĩnh viễn** xoá hẳn một task, không hoàn tác được.
- **Dọn task đã quá hạn** xoá những task đã hết 30 ngày.
- **Dọn sạch thùng rác** xoá hết, không chờ hết hạn.

Một điều nên biết: việc dọn tự động chỉ xảy ra khi app khởi động và khi bạn mở tab
Thùng rác. Nghĩa là không task nào bị xoá **sớm** hơn 30 ngày, nhưng có thể bị xoá
**muộn** hơn nếu bạn lâu không mở app. Đây là hạn chế đã biết, sẽ hết khi hệ thống
có bộ chạy định kỳ.

## Sao lưu và chuyển máy

Tab **Dữ liệu** cho tải về hai định dạng:

| Định dạng | Dùng để |
|---|---|
| **JSON** | Sao lưu thật. Giữ đủ tag, nhật ký thay đổi, trạng thái thùng rác |
| **CSV** | Mở bằng Excel để xem hoặc sửa hàng loạt |

CSV không giữ được nhật ký thay đổi và tag bị nối bằng dấu chấm phẩy, nên **đừng
dùng CSV làm bản sao lưu chính**. Dùng JSON.

Khi nhập lại có hai chế độ:

- **Thêm vào** — giữ dữ liệu hiện có. Dự án trùng mã bị bỏ qua. Task đang ở trong
  thùng rác của file nguồn cũng bị bỏ qua, để việc nhập không tự dựng lại thứ bạn
  đã xoá.
- **Thay toàn bộ** — xoá hết dữ liệu hiện tại rồi nạp từ file. Nên tải bản JSON về
  trước khi làm.

Sửa CSV bằng Excel thì lưu ý: cột dự án là **mã dự án** chứ không phải tên, và
nhập CSV task sẽ không tự tạo dự án mới. Nếu cần dự án mới thì nhập CSV dự án
trước.

## Ba tab để hiểu dự án đang build

Nhóm **Dự án này** trên thanh điều hướng:

- **Kiến trúc** — năm sơ đồ về cách app hoạt động: container nói với nhau ra sao,
  một lần ghi dữ liệu đi qua đâu, task chuyển trạng thái theo luật nào.
- **Lộ trình** — tiến độ năm giai đoạn. Có trạng thái "Chưa verify" nghĩa là code
  đã viết nhưng chưa từng chạy, nên con số tiến độ thận trọng hơn cảm giác.
- **Tài liệu** — đọc trực tiếp file markdown trong repo, gồm cả tài liệu này.

Hai nhóm **Tích hợp** và **Vận hành** đang mờ vì thuộc giai đoạn sau, chưa có
trang thật.

## Mẹo dùng

**Ghi ngay, sắp xếp sau.** Gõ tiêu đề rồi bấm Thêm là đủ. Đừng bắt mình điền đủ
trường mỗi lần, vì như vậy bạn sẽ ngại ghi và cuối cùng không ghi gì.

**Giới hạn việc Đang làm.** Ba đến bốn task cùng lúc là nhiều rồi. Nếu nhóm Đang
làm dài ra thì thường là bạn đang nhảy qua lại giữa các việc chứ không phải làm
nhanh hơn.

**Dùng Bị chặn thật sự.** Ghi rõ đang chờ gì vào mô tả. Một task Bị chặn không có
lý do sẽ thành task bị bỏ quên.

**Điền ước lượng nếu muốn số liệu tiến độ có ý nghĩa.** Không điền thì tiến độ chỉ
đếm số lượng task, coi task 5 phút bằng task 3 ngày.

**Tag theo ngữ cảnh, không theo dự án.** Dự án đã có trường riêng. Tag hữu ích khi
nó cắt ngang nhiều dự án, ví dụ `cần-tập-trung`, `chờ-phản-hồi`, `việc-nhanh`.

## Sự cố thường gặp

**Trang hiện "Không đọc được dữ liệu từ core API".**
App đang ở chế độ `api` nhưng backend chưa chạy. Hai cách: dựng backend bằng
`make bootstrap`, hoặc đổi `DATA_SOURCE=file` trong `apps/web/.env.local` để chạy
độc lập với file JSON.

**Có banner vàng nói dữ liệu sẽ mất khi restart.**
Đang ở chế độ `memory`. Đổi sang `DATA_SOURCE=file` trong
`apps/web/.env.local` rồi khởi động lại.

**Task vừa xoá đâu rồi?**
Ở tab Thùng rác, giữ 30 ngày. Bấm Phục hồi.

**Xoá xong mới thấy cần lại, nhưng đã bấm Xoá vĩnh viễn.**
Không phục hồi được. Nếu bạn có bản JSON sao lưu thì nhập lại bằng chế độ Thêm
vào, nhưng nhớ là task trong thùng rác của file nguồn sẽ bị bỏ qua.

**Số "xong hôm nay" trông sai.**
Kiểm tra múi giờ hiển thị. Mặc định là `Asia/Ho_Chi_Minh`, đổi bằng
`NEXT_PUBLIC_DISPLAY_TZ`. Biến này được nhúng lúc build nên đổi rồi phải khởi
động lại.

**Nhập CSV báo bỏ qua nhiều dòng.**
Thông báo có ghi số dòng và lý do. Hay gặp nhất là thiếu tiêu đề, hoặc mã dự án
trong file chưa tồn tại. Nhập CSV dự án trước rồi nhập lại CSV task.

**Tag nhập vào bị đổi khác.**
Đó là chuẩn hoá tự động, không phải lỗi. Chữ thành chữ thường và khoảng trắng
thành dấu gạch ngang để tag không bị phân mảnh thành nhiều biến thể.
