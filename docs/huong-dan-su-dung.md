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

## Sổ tay

Tab **Sổ tay** là chỗ dán lại câu lệnh, câu SQL và đoạn cấu hình đã mất công tìm
ra, để lần sau copy chứ không phải dò lại. Khác task ở chỗ nó không có hạn và
không có trạng thái: đây là tài liệu tham khảo, không phải việc cần làm.

### Các trường khi nhập

| Trường | Ý nghĩa |
|---|---|
| **Tiêu đề** | Tên ngắn để tìm lại, tối đa 300 ký tự |
| **Loại** | Câu lệnh, SQL, Ghi chú, Cấu hình, Đoạn code. Chỉ để tô màu và lọc |
| **Nội dung để copy** | Phần thật sự được copy. Giữ nguyên xuống dòng và thụt lề |
| **Nơi áp dụng** | Chạy ở đâu: tên máy, tên database, môi trường |
| **Vì sao cần** | Ghi lại lý do, để sáu tháng sau đọc còn hiểu |
| **Dự án** | Gắn vào một dự án, không bắt buộc |
| **Tag** | Cách nhau bằng dấu phẩy |
| **Ghim lên đầu** | Cho thứ dùng hằng ngày |
| **Đánh dấu cẩn thận** | Hỏi lại một lần trước khi copy |

Tách **Nội dung** khỏi **Vì sao cần** là có lý do: bấm Copy chỉ lấy đúng phần
nội dung, không kéo theo văn xuôi giải thích.

### Tìm lại

Ô tìm kiếm soi cả **nội dung**, không chỉ tiêu đề. Đây là cách dùng thật: thường
bạn chỉ nhớ một mẩu trong câu lệnh chứ không nhớ đã đặt tên là gì. Gõ `pg_dump`
hay `deleted_at` là ra.

Sắp xếp được theo Sửa gần nhất, Hay dùng nhất, Dùng gần nhất, Mới tạo, hoặc tên
A→Z. Mục đã ghim **luôn** đứng trước, bất kể chọn sắp xếp nào.

Bộ lọc nằm trong địa chỉ trang, nên một bộ lọc hay dùng có thể bookmark lại.

### Hai cảnh báo tự động

**Lệnh nguy hiểm.** Khi bạn gõ nội dung, app soi vài dấu hiệu quen như `rm -rf`,
`DROP TABLE`, `TRUNCATE`, `DELETE` thiếu `WHERE`, `docker compose down -v`. Nếu
thấy, ô *Đánh dấu cẩn thận* được tích sẵn và hiện lý do. Đây chỉ là gợi ý: bạn bỏ
tích được, và ngược lại tự tích cho thứ mà app không nhận ra. Mục có dấu này sẽ
hỏi xác nhận một lần trước khi copy.

**Có thể chứa bí mật.** Nếu nội dung trông như có mật khẩu, API key, hay
connection string nhúng mật khẩu, app sẽ nhắc. Lý do thật sự quan trọng:

> Sổ tay lưu **văn bản thuần, không mã hoá**, trong Postgres hoặc trong file JSON.
> Ai đọc được database hoặc file backup là đọc được mọi thứ trong đó.

Cách làm đúng là để chỗ của giá trị thật, không phải giá trị thật:

```bash
# nên
psql -U builder -d builder_ai   # mật khẩu lấy từ $PGPASSWORD trong .env

# không nên
PGPASSWORD=matkhauthat psql -U builder -d builder_ai
```

### App không bao giờ chạy nội dung note

Đây là điều cần nói thẳng: lưu một câu lệnh vào sổ tay **không** làm nó chạy.
Không có nút nào trong app thực thi nội dung note, kể cả với loại Câu lệnh hay
SQL. Nội dung chỉ là chuỗi ký tự trong database, và nút Copy chỉ đưa nó vào
clipboard. Việc dán vào terminal và bấm Enter vẫn là quyết định của bạn.

Một mục chứa `rm -rf /` nằm trong sổ tay là vô hại. Nó chỉ nguy hiểm khi bạn tự
copy rồi tự chạy.

## Thùng rác

Xoá task và xoá mục sổ tay đều là **xoá mềm**. Chúng vào thùng rác và được giữ
**30 ngày**. Trong thời gian đó chúng không xuất hiện ở bất kỳ đâu ngoài tab
Thùng rác: không ở agenda, không trong danh sách, không trong kết quả tìm kiếm,
không tính vào thống kê.

Tab **Thùng rác** chia hai mục riêng, **Task** và **Sổ tay**, mỗi mục có bộ nút
của nó. Ở cả hai:

- Mỗi bản ghi hiện **số ngày còn lại**. Dưới 7 ngày thì số chuyển vàng, dưới 3
  ngày chuyển đỏ.
- **Phục hồi** đưa nó về trạng thái trước khi xoá.
- **Xoá vĩnh viễn** xoá hẳn một bản ghi, không hoàn tác được.
- **Dọn đã quá hạn** xoá những bản ghi đã hết 30 ngày.
- **Dọn sạch** xoá hết, không chờ hết hạn.

Mục sổ tay trong thùng rác chỉ hiện **dòng đầu** của nội dung. Đó là đủ để nhận
ra mình đã xoá cái gì; cần đọc đủ thì phục hồi rồi xem ở tab Sổ tay.

Một điều nên biết: việc dọn tự động chỉ xảy ra khi app khởi động và khi bạn mở tab
Thùng rác. Nghĩa là không bản ghi nào bị xoá **sớm** hơn 30 ngày, nhưng có thể bị
xoá **muộn** hơn nếu bạn lâu không mở app. Đây là hạn chế đã biết, sẽ hết khi hệ
thống có bộ chạy định kỳ.

## Sao lưu và chuyển máy

Tab **Dữ liệu** cho tải về hai định dạng:

| Định dạng | Dùng để |
|---|---|
| **JSON** | Sao lưu thật. Giữ đủ task, dự án, sổ tay, tag, nhật ký thay đổi, trạng thái thùng rác |
| **CSV** | Mở bằng Excel để xem hoặc sửa hàng loạt. Có ba loại: task, dự án, sổ tay |

CSV không giữ được nhật ký thay đổi và tag bị nối bằng dấu chấm phẩy, nên **đừng
dùng CSV làm bản sao lưu chính**. Dùng JSON.

Khi nhập lại có hai chế độ:

- **Thêm vào** — giữ dữ liệu hiện có. Dự án trùng mã bị bỏ qua. Mục sổ tay trùng
  cả tiêu đề và nội dung cũng bị bỏ qua, nên nhập lại cùng một file backup hai
  lần không làm nhân đôi sổ tay. Task và mục sổ tay đang ở trong thùng rác của
  file nguồn thì bị bỏ qua, để việc nhập không tự dựng lại thứ bạn đã xoá.
- **Thay toàn bộ** — xoá hết dữ liệu hiện tại rồi nạp từ file. Nên tải bản JSON về
  trước khi làm. Lưu ý: thay từ **CSV task** chỉ thay task, còn dự án và sổ tay
  giữ nguyên; thay từ **CSV sổ tay** thì ngược lại.

Sửa CSV bằng Excel thì lưu ý: cột dự án là **mã dự án** chứ không phải tên, và
nhập CSV task hay CSV sổ tay đều không tự tạo dự án mới. Nếu cần dự án mới thì
nhập CSV dự án trước.

Nội dung nhiều dòng của sổ tay được bọc trong dấu ngoặc kép theo RFC 4180, nên
Excel mở ra vẫn thấy đúng một ô nhiều dòng.

## Các tab để hiểu dự án đang build

Nhóm **Dự án này** trên thanh điều hướng:

- **Kiến trúc** — năm sơ đồ về cách app hoạt động: container nói với nhau ra sao,
  một lần ghi dữ liệu đi qua đâu, task chuyển trạng thái theo luật nào.
- **Lộ trình** — tiến độ năm giai đoạn. Có trạng thái "Chưa verify" nghĩa là code
  đã viết nhưng chưa từng chạy, nên con số tiến độ thận trọng hơn cảm giác.
- **Tài liệu** — đọc trực tiếp file markdown trong repo, gồm cả tài liệu này.
- **Hệ thống** — tình trạng sống/chết của database và Redis, phiên bản đang
  chạy, danh sách container Docker và vai trò từng cái, và vài con số cấu
  hình (giới hạn request, số ngày giữ thùng rác). Có nút **Hiện** cho một
  khối thông tin kỹ thuật (URL nội bộ, tên biến môi trường) — mặc định ẩn,
  không phải vì đó là bí mật mà vì không cần thấy ngay. Mật khẩu và khoá API
  **không** hiển thị ở đây hay bất kỳ đâu trên web — mục **Tài khoản** chỉ
  ghi tên biến và lệnh để người có quyền truy cập máy tự tra, không có mật
  khẩu mặc định đặt sẵn (mỗi lần dựng stack sinh khoá ngẫu nhiên riêng).
  Trang này cũng gom sẵn link tới các tài liệu deploy nếu bạn cần dựng thêm
  máy hoặc chia sẻ cho người khác dùng.

Hai nhóm **Tích hợp** và **Vận hành** đang mờ vì thuộc giai đoạn sau, chưa có
trang thật.

## Làm việc với AI agent để phát triển dự án

Phần này dành cho người **phát triển** repo, không phải người dùng app.

1. **Mở repo bằng Claude Code** ở thư mục gốc (`claude`). Agent tự đọc `CLAUDE.md`,
   `AGENTS.md` và nạp luật trong `.agents/rules/` theo file đang sửa. Bắt đầu session
   mới bằng câu: *"Đọc `docs/AI_HANDOFF_STATE.md` rồi tóm tắt trạng thái hiện tại"*.
2. **Việc nhỏ** (sửa 1–2 file) cứ nói thẳng, agent chính tự làm.
3. **Việc lớn chạm nhiều tầng** (DB + API + web): nhờ agent gọi `architect` ra spec trong
   `docs/specs/`, bạn đọc và chốt, rồi mới cho `backend-dev` và `frontend-dev` code.
   Cuối cùng `code-reviewer` soát diff trước khi commit.
4. **Lệnh nên dùng** đều có trong `make` (chạy `make` để xem), ví dụ `make smoke`,
   `make lint`, `make migration m="..."`.
5. **Commit và push**: agent commit theo Conventional Commits khi bạn cho phép;
   `git push` luôn hỏi lại bạn. Force push và xoá volume Docker bị chặn cứng.
6. **Mô tả việc rõ ràng** sẽ nhanh hơn nhiều: nêu route web, API cần gọi, và kết quả mong đợi.

Đọc thêm trong tab **Tài liệu**: *Claude CLI Quickstart* (cách chạy và các hàng rào an toàn)
và *Demo: Multi-Agent Workflow* (quy trình 7 bước và prompt mẫu).

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

**Dán vào Sổ tay ngay lúc vừa tìm ra.** Thời điểm bạn chắc chắn sẽ quên là lúc
vừa làm xong và đang thấy nó hiển nhiên. Kèm một dòng *Vì sao cần* thì sáu tháng
sau đọc lại còn hiểu, chứ không chỉ là một chuỗi ký tự lạ.

**Ghim thứ dùng hằng ngày, đừng ghim mọi thứ.** Ghim mười lăm mục thì việc ghim
hết ý nghĩa. Còn lại cứ để sắp xếp theo Hay dùng nhất lo.

**Tag theo ngữ cảnh, không theo dự án.** Dự án đã có trường riêng. Tag hữu ích khi
nó cắt ngang nhiều dự án, ví dụ `cần-tập-trung`, `chờ-phản-hồi`, `việc-nhanh`.

## Dùng từ máy khác trong nhà

Muốn mở app trên điện thoại hoặc laptop khác, không chỉ máy đang chạy nó? Nhờ
người quản trị máy chạy app bật chia sẻ LAN (`make lan-up` — xem README mục
"Chia sẻ trong LAN"), rồi mở `http://<IP máy đó>:3000` trên thiết bị khác
cùng mạng wifi/dây.

Cần biết trước khi dùng theo cách này: **ai mở được địa chỉ đó cũng dùng app
y như bạn** — không có tài khoản riêng ở giai đoạn hiện tại, nên họ xem và sửa
được mọi task, mọi mục sổ tay, kể cả mục đánh dấu "cẩn thận". Chỉ phù hợp khi
mọi thiết bị trong mạng đó là người bạn tin tưởng (ví dụ cả nhà dùng chung một
danh sách việc). Nếu đang ở mạng công cộng hoặc dùng chung với người lạ, đừng
nhờ bật chia sẻ.

## Sự cố thường gặp

**Trang hiện "Không đọc được dữ liệu từ core API".**
App đang ở chế độ `api` nhưng backend chưa chạy. Hai cách: dựng backend bằng
`make bootstrap`, hoặc đổi `DATA_SOURCE=file` trong `apps/web/.env.local` rồi
khởi động lại `npm run dev` để chạy độc lập với file JSON (không cần Postgres).

**Có banner vàng nói dữ liệu sẽ mất khi restart.**
Đang ở chế độ `memory`. Đổi sang `DATA_SOURCE=file` trong
`apps/web/.env.local` rồi khởi động lại.

**Không tìm thấy chỗ đổi `DATA_SOURCE` trên web, phải sửa file ở đâu?**
Không có nút bấm đổi trên web — việc đổi cần Next.js khởi động lại để nạp
biến môi trường mới. Chạy app qua Docker thì dùng `make use-db` /
`make use-local` (xem tab **Dữ liệu** trên web, mục "Đổi nguồn dữ liệu", hoặc
README mục "Ba nguồn dữ liệu"). Chạy bằng `npm run dev` không qua Docker thì
sửa tay dòng `DATA_SOURCE=` trong `apps/web/.env.local`, rồi tắt và chạy lại
`npm run dev` — sửa file không tự áp dụng, phải khởi động lại.

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

## Tính năng Dữ liệu Nâng cao (Quest Data, Chrome History, Backups)

### 1. Đồng bộ Dữ liệu từ JIRA & Google Sheets
Tại trang **Dữ liệu**, bạn có thể tải lên file Export (`.xlsx`, `.csv`) từ JIRA hoặc dán trực tiếp đường link **Google Sheets** (Lưu ý: Share ở chế độ "Bất kỳ ai có link đều xem được"). 
Hệ thống sẽ tự động bóc tách cực kỳ thông minh theo các nguyên tắc:
- **Tự tạo Dự án theo Company:** Hệ thống tự động đọc cột `Company` trong file để sinh ra các Dự án tương ứng, và gán một màu sắc ngẫu nhiên tuyệt đẹp cho mỗi dự án mới.
- **Tự động gắn Tag toàn diện:** Mỗi task sẽ được gắn sẵn tag từ các nguồn: cột `Company`, cột `Projects`, cột `Labels`, VÀ toàn bộ các từ nằm trong `[ngoặc vuông]` của Tiêu đề (Summary).
- **Chống trùng lặp tuyệt đối:** Bạn có thể ấn đồng bộ 1000 lần mà không sợ rác dữ liệu. Hệ thống tự động gộp Dự án (không phân biệt hoa/thường), gộp Task (theo JIRA Issue Key hoặc theo tên), và chuẩn hóa toàn bộ Tag.

### 2. Trích xuất Lịch sử Web (Chrome)
Hệ thống có khả năng sao lưu lịch sử duyệt web của Google Chrome cục bộ trên máy tính (hỗ trợ Mac, Windows, Linux).
- Vào trang **Dữ liệu** -> Bấm nút **Trích xuất Chrome History**.
- Chuyển sang tab **Lịch sử duyệt web**: Tại đây, bạn có thể xem lại toàn bộ các link đã từng truy cập, kết hợp với bộ lọc thời gian (1 ngày, 3 ngày, 1 tháng...) và thanh tìm kiếm cực kỳ mượt mà. Tất cả dữ liệu đều được format hiển thị chuẩn múi giờ UTC+7.

### 3. Vùng Nguy Hiểm & Cơ chế Auto-Backup
Nằm dưới cùng trang **Dữ liệu**, khu vực "Danger Zone" cho phép bạn:
- Xóa tùy chọn từng phần: Chỉ xóa Task, Dự án, Sổ tay, hoặc Lịch sử Chrome thay vì phải xóa toàn bộ.
- **Auto-Backup thông minh:** Mọi thao tác xóa dữ liệu tại khu vực này đều kích hoạt hệ thống **Tự động chụp lại bản sao lưu (Backup)** trước khi thực thi. 
  - Bản sao lưu sẽ được lưu thành file JSON kèm timestamp tại thư mục `data/backups/`. 
  - Để tiết kiệm dung lượng, hệ thống luôn tự động dọn rác và **chỉ giữ lại duy nhất 1 bản backup gần nhất**.
- Nếu bạn lỡ tay xóa nhầm, chỉ cần lấy file backup đó và tải lên ở khung **Khôi phục dữ liệu từ Backup (JSON)** (Màu cam) là mọi thứ sẽ phục hồi nguyên trạng 100%.
