# Repo pipeline: CI trước khi merge (SPEC §9.5)

Backend mở PR vào repo riêng với bộ file Reviewer đã duyệt. CI kiểm lại nội dung commit, rồi chạy `dbt parse`.
Người có quyền merge quyết định đưa code vào `main`; deployer trên VM kéo `main` bằng khóa chỉ đọc, kiểm manifest
lần nữa rồi cài vào Dagster production. CI không cần PAT, khóa SSH hay credential nguồn dữ liệu.

## 1. Tạo repo và xuất bộ khung

1. Tạo repo `<owner>/atomesus-pipelines` trên GitHub, chọn **Add a README file** để có commit đầu tiên. Đặt nhánh
   mặc định là `main`. Repo trống chưa có ref nên backend không thể tạo nhánh pipeline.
2. Kiểm tra GitHub Actions chạy được và gói GitHub có branch protection cho loại repo đã chọn. Repo public dùng
   được với GitHub Free; repo private cần gói hỗ trợ. Xem [điều kiện branch protection](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches).
3. Clone repo pipeline vào thư mục riêng. Trong thư mục repo **app**, chạy:

   ```bash
   python scripts/export_pipeline_repo.py ../atomesus-pipelines
   ```

   Script sinh `README.md` (hướng dẫn này), `.github/workflows/ci.yml`, `ci/check_pr.py`, `ci/parse_project.py`,
   `ci/manifest.py`, `_scaffold/dbt_project/`, `CODEOWNERS`, `requirements-ci.txt`. Manifest là bản sao **nguyên byte**
   của `src/deployer/manifest.py`; scaffold lấy từ `dbt_project/` của app, bỏ `target/`, `logs/`, file DuckDB.
   Requirements giữ đúng ràng buộc dbt của app: hiện là `dbt-core>=1.9,<1.11`, `dbt-duckdb>=1.9,<2`, chưa phải khóa
   `==` một bản cụ thể. Khi app ghim phiên bản cụ thể, xuất lại sẽ dùng chính các phiên bản đó.
4. Sửa `CODEOWNERS`: bỏ dấu `#` ở các dòng mẫu và thay `@nguoi-duyet` bằng người/team có quyền write chịu trách nhiệm.
   Phải có owner cho `/.github/`, `/ci/` và `/CODEOWNERS` để thay đổi workflow, bộ kiểm và chính danh sách owner
   đều cần người phụ trách review. Giữ dòng `*` để mọi file khác cũng có owner; kiểm GitHub không báo lỗi cú pháp
   và tự yêu cầu đúng owner khi mở PR. Xem [CODEOWNERS](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners).
   Commit bộ khung vào repo pipeline và push `main` **trước khi** bật bảo vệ nhánh. Những lệnh commit/push ở đây
   do quản trị viên thực hiện trong repo pipeline, không phải repo app.

Chạy lại exporter ghi đè đúng các file được xuất, kể cả `README.md` và `CODEOWNERS`; giữ nguyên pipeline và mọi
file khác. Sao lưu tùy chỉnh CODEOWNERS rồi áp dụng lại sau khi xuất. Script không dọn file dư từ lần xuất cũ.

## 2. Bật branch protection cho main

Trong **Settings → Branches → Add branch protection rule**, nhập `main`:

1. Bật **Require a pull request before merging**, **Require approvals** = **1**, **Require review from Code Owners**.
   Code owner phải là người; tài khoản cấp PAT không được nằm trong CODEOWNERS. Xác nhận các owner của `.github/`
   và `ci/` ở bước 1 đã có hiệu lực trên `main`; bật yêu cầu code owner review là bắt buộc, không chỉ gợi ý reviewer.
2. Bật **Dismiss stale pull request approvals when new commits are pushed** và **Require approval of the most
   recent reviewable push** để commit mới cần người khác duyệt lại.
3. Bật **Require status checks to pass before merging**, **Require branches to be up to date before merging**,
   chọn check cố định **`pipeline-ci`** của workflow **CI**, nguồn **GitHub Actions**. Nếu chưa thấy check, mở PR
   đầu tiên do app tạo, chờ CI chạy rồi quay lại chọn. Chưa cấu hình xong thì chưa merge PR nào.
4. Bật **Do not allow bypassing the above settings** (kể cả admin). Không cấp ai quyền bypass PR; không bật
   **Allow force pushes** hoặc **Allow deletions**. Như vậy push thẳng bị chặn và PR cần approval + CI.
5. Với repo organization, bật **Restrict who can push to matching branches**, chỉ thêm người/team thực hiện merge;
   loại tài khoản cấp PAT khỏi danh sách. Việc này chặn cả cập nhật `main` qua merge của tài khoản đó.

Tham khảo [các lựa chọn bảo vệ nhánh](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/managing-a-branch-protection-rule).
Tên job phải duy nhất trong repo. Tắt auto-merge; người phụ trách kiểm PR rồi bấm merge. Workflow chỉ xử lý PR vào
nhánh mặc định, dùng Python 3.11 và `contents: read`, không khai báo secrets, không lưu credential checkout.
Script, requirements, profile và macro lấy từ **base**; head chỉ được đọc qua object Git.

Với sự kiện `pull_request`, GitHub chạy định nghĩa workflow từ **merge ref của PR** (`refs/pull/<số>/merge`),
không phải bản workflow trên base. Checkout base trong các step chỉ bảo vệ script khi định nghĩa workflow này
được giữ nguyên; CI không tự chặn được PR sửa `.github/workflows/` để bỏ kiểm tra hoặc báo check xanh giả.
Chốt bảo vệ là PAT backend **không có quyền Workflows** (GitHub từ chối push thay đổi workflow bằng token đó),
CODEOWNERS cho `.github/` và `ci/`, cùng branch protection bắt buộc code owner review. Người dùng credential
khác vẫn có thể đề xuất sửa workflow; owner phải kiểm diff trước khi merge, không chỉ nhìn check xanh.
Xem [sự kiện pull_request](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#pull_request).

## 3. Tạo fine-grained PAT cho backend

1. Dùng tài khoản chuyên tạo PR, có quyền write repo pipeline, không có quyền admin/bypass. GitHub → **Settings →
   Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**.
2. Đặt tên, hạn dùng ngắn phù hợp vận hành; chọn Resource owner đúng. **Repository access → Only select
   repositories**: chỉ `<owner>/atomesus-pipelines`.
3. **Repository permissions**: **Contents: Read and write**, **Pull requests: Read and write**, **Metadata: Read-only**.
   Để **Workflows: No access**, không cấp Administration, Actions hay quyền repo app. Không thêm Workflows để
   xử lý lỗi push: GitHub yêu cầu quyền này khi tạo/cập nhật `.github/workflows/`, nên từ chối token backend sửa CI.
   Xem [quyền cập nhật file workflow](https://docs.github.com/en/rest/repos/contents#create-or-update-file-contents).
   Nếu org yêu cầu duyệt token, chờ được duyệt.
4. Lưu token vào cấu hình bí mật của backend trên VM với tên `PIPELINE_GITHUB_TOKEN`. Không đưa vào repo,
   RunReport, CI, agent hoặc sandbox. Đặt lịch thay token trước hạn; thu hồi ngay khi lộ.

**Vì sao backend không merge:** mã GitHub client chỉ tạo nhánh/commit/PR, không gọi API merge. PAT có Contents RW
**vẫn có khả năng gọi API merge về kỹ thuật**; GitHub không có quyền PAT riêng “tạo PR nhưng cấm merge”. Chốt chặn
là branch protection: CI và approval người bắt buộc; ở org, giới hạn người cập nhật `main` loại tài khoản PAT sẽ
chặn token merge ngay cả sau approval. Với repo cá nhân chỉ dùng protection cơ bản, token có thể merge sau khi
đủ điều kiện; không coi đó là bảo đảm cấm merge tuyệt đối. Nếu cần bảo đảm này, dùng repo org có giới hạn người
push/merge và Actions hoạt động. Xem [quyền fine-grained PAT](https://docs.github.com/en/rest/authentication/permissions-required-for-fine-grained-personal-access-tokens).

## 4. Tạo webhook về backend

1. Repo pipeline → **Settings → Webhooks → Add webhook**.
2. **Payload URL**: `https://<ten-mien>/api/v1/webhooks/github`. Route này phải được reverse proxy đưa tới backend;
   kiểm cấu hình proxy của bản triển khai, không dùng URL nội bộ Docker cho GitHub.
3. **Content type**: `application/json`. Sinh một secret ngẫu nhiên riêng, lưu cùng giá trị ở webhook và
   `PIPELINE_GITHUB_WEBHOOK_SECRET` trên backend. Bật SSL verification.
4. **Let me select individual events**: chọn **Pull requests** (`pull_request`), **Check suites** (`check_suite`),
   **Workflow runs** (`workflow_run`), bật **Active** rồi lưu.
5. Trong **Recent deliveries**, kiểm ping/delivery nhận 2xx. Khi route webhook của backend đã được triển khai,
   CI hoàn tất, PR merge/đóng phải cập nhật run; delivery sai HMAC phải bị từ chối. Task bộ khung không cài route này.

Các bước GitHub: [tạo webhook](https://docs.github.com/en/webhooks/using-webhooks/creating-webhooks).

## 5. Tạo deploy key chỉ đọc cho deployer

Trên VM dưới tài khoản chạy deployer, sinh khóa riêng chỉ dùng cho repo pipeline:

```bash
ssh-keygen -t ed25519 -C atomesus-pipeline-readonly -f ~/.ssh/atomesus_pipeline_readonly
chmod 600 ~/.ssh/atomesus_pipeline_readonly
```

Repo pipeline → **Settings → Deploy keys → Add deploy key**: đặt tên, dán **public key** từ file `.pub`,
**không chọn Allow write access**. Private key ở VM/deployer, không đưa vào backend hay GitHub Actions.
Thiết lập SSH `IdentityFile` cho khóa này, `IdentitiesOnly yes`, xác minh fingerprint GitHub qua nguồn chính thức
trước khi thêm vào `known_hosts`; không tắt kiểm host key. Deployer clone/fetch từ
`git@github.com:<owner>/atomesus-pipelines.git`, chỉ theo `main`.

Mount khóa và known_hosts chỉ đọc cho deployer, volume Dagster production chỉ deployer được ghi; backend đọc
volume đó với `:ro`. Deployer không nhận PAT tạo PR. Xem [deploy keys](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/managing-deploy-keys).

## 6. Đặt cấu hình trên VM và kiểm toàn luồng

Đưa các giá trị vào cấu hình môi trường riêng của từng service, quyền đọc chỉ tài khoản vận hành; ví dụ giá trị
dưới đây là chỗ trống, **không dùng làm secret thật**:

```dotenv
# Backend
APP_ENV=production
PIPELINE_GITHUB_REPO=<owner>/atomesus-pipelines
PIPELINE_GITHUB_TOKEN=<fine-grained-PAT>
PIPELINE_GITHUB_WEBHOOK_SECRET=<secret-webhook-ngau-nhien>
PIPELINE_DEPLOYER_SECRET=<secret-callback-ngau-nhien-khac-webhook>
```

Deployer dùng cùng `PIPELINE_DEPLOYER_SECRET` để ký HMAC callback, URL callback nội bộ
`http://backend:8000/api/v1/deployments/callback`, repo SSH và nhánh `main`. Tên biến cho đường dẫn SSH,
clone dir, callback URL theo cấu hình service deployer được triển khai ở task DEPLOYER-PROD; bộ khung này không
tự tạo service hoặc tự bật webhook. Backend production phải giữ các cổng an toàn `APP_ENV` và xác thực thật.
Sau khi đổi môi trường, tạo lại container liên quan để nhận cấu hình mới; không chỉ restart container cũ.

1. Engineer tạo run từ spec mẫu, Reviewer khác người tạo duyệt rồi bấm Deploy: có PR tới `main`.
2. `pipeline-ci` xanh và người phụ trách so `run_id/version/files_hash/reviewer/approved_at` với RunReport trong app
   rồi approve. Chưa approval hoặc CI đỏ thì merge phải bị GitHub chặn.
3. Thử sửa file SQL trên nhánh PR: CI báo sha256 không khớp và approval cũ bị hủy. Không sửa tay manifest để “sửa CI”;
   quay về app tạo version mới, chạy thử và duyệt lại.
4. Người trong danh sách merge bấm merge. Deployer kéo commit, kiểm manifest, cài nguyên tử và gửi callback HMAC.
   Chỉ sau callback thành công mới coi là DEPLOYED.

Kiểm offline trong repo pipeline (thay SHA và model):

```bash
python -m pip install -r requirements-ci.txt
python ci/check_pr.py --base <base-sha> --head <head-sha>
python ci/parse_project.py fct_daily_orders --head <head-sha> --timeout 120
```

`check_pr.py` so `base...head` (merge base), từ chối thay đổi ngoài `pipelines/<model>/`, file thừa/thiếu,
symlink/submodule/file thực thi, JSON sai và mọi lệch hash/chữ ký giữa manifest và report. Parse dùng project tạm,
có timeout và log tối đa 4 KB; không chạy ingestion hay Dagster và không kết nối nguồn.
Chữ ký duyệt trong hợp đồng hiện là metadata + hash, **không phải chữ ký mật mã**: nếu ai sửa đồng thời code,
manifest và report cho nhất quán thì CI độc lập không chứng minh được đó là chữ ký backend đã lưu. Người duyệt PR
phải đối chiếu bằng chứng trong app; CI không có secret để xác thực nguồn chữ ký.

## 7. PR bảo trì CI, dbt và CODEOWNERS

`check_pr.py` cố ý từ chối PR sửa script/workflow/scaffold, `requirements-ci.txt` hay `CODEOWNERS` vì chúng nằm
ngoài `pipelines/<model>/`. Không nới quy tắc checker hoặc sửa workflow để giả check xanh cho PR bảo trì.
Quản trị viên dùng quy trình ngoại lệ sau, bằng tài khoản cá nhân có quyền admin, không dùng PAT backend:

1. Tạo nhánh `maintenance/<noi-dung>` từ `main`, mở PR chỉ chứa thay đổi bảo trì. Khi nâng dbt, cập nhật ràng buộc
   đã duyệt ở repo app rồi xuất lại bộ khung; áp dụng lại owner thật trước khi mở PR. Giữ tên check `pipeline-ci`.
2. Nhờ code owner khác người tạo review diff, kể cả workflow và CODEOWNERS. Chạy checker/parse mới trên một cặp
   base/head của PR pipeline hợp lệ trong clone cục bộ (lệnh ở bước 6), thử một thay đổi hash để xác nhận bị từ chối.
   Ghi SHA đã review, kết quả kiểm, lý do ngoại lệ, người thực hiện và thời gian dự kiến vào PR/biên bản vận hành.
   Check đỏ vì file bảo trì ngoài phạm vi là dự kiến; lỗi parse/manifest thật phải được xử lý trước.
3. Tạm dừng tạo PR từ backend và mọi merge pipeline trong cửa sổ bảo trì. Lưu cấu hình branch protection hiện tại.
   Admin vào rule `main`, tạm bỏ **Do not allow bypassing the above settings**, không cấp bypass cho tài khoản PAT
   và không bật force push/deletion. Nếu có ruleset khác chặn admin bypass, giữ nguyên bảo vệ và xử lý ngoại lệ
   qua người quản lý ruleset trước; không tắt tất cả các rule để thử.
4. Admin kiểm SHA PR vẫn đúng bản code owner đã duyệt rồi dùng quyền bypass để merge **chỉ PR bảo trì đó**.
   Ghi commit merge và thời điểm vào biên bản. Bypass có thể bỏ qua cả review lẫn check và mở khả năng push thẳng
   cho admin trong cửa sổ này; vì vậy phải có review người trước và giới hạn cửa sổ, không merge PR nào khác.
5. Ngay sau merge (hoặc khi hủy bảo trì), bật lại **Do not allow bypassing the above settings**. Đối chiếu cấu hình
   đã lưu: require PR, 1 approval, code owner review, stale approval, required `pipeline-ci`, giới hạn người merge,
   force push/deletion vẫn tắt. Mở PR pipeline mẫu, xác nhận CI và yêu cầu review hoạt động rồi mới tiếp tục backend.
   Ghi bằng chứng khôi phục bảo vệ vào biên bản; chưa khôi phục xong thì vẫn dừng tạo PR/merge.

GitHub mô tả [quyền admin bypass và cách chặn bypass](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches).
