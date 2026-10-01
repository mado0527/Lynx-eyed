from django.db import models


# 1. 管理者情報テーブル (admin_info)
class AdminInfo(models.Model):
    admin_id = models.AutoField(primary_key=True, verbose_name="管理者ID")
    username = models.CharField(max_length=150, unique=True, verbose_name="ユーザー名")
    password = models.CharField(max_length=128, verbose_name="パスワード")
    
    ROLE_CHOICES = (
        (0, '管理者'),
        (1, '共同研究者'),
    )
    role = models.IntegerField(choices=ROLE_CHOICES, verbose_name="管理者区分")

    class Meta:
        db_table = 'admin_info'
        verbose_name = '管理者情報'

    def __str__(self):
        return self.username


# 2. 場所マスターテーブル (location_master)
class LocationMaster(models.Model):
    location_id = models.AutoField(primary_key=True, verbose_name="場所ID")
    name = models.CharField(max_length=100, verbose_name="場所名")
    capacity = models.IntegerField(verbose_name="最大定員")

    class Meta:
        db_table = 'location_master'
        verbose_name = '場所マスター'

    def __str__(self):
        return f"{self.name} (定員: {self.capacity}名)"


# 3. 端末情報テーブル (device_info)
class DeviceInfo(models.Model):
    device_id = models.AutoField(primary_key=True, verbose_name="端末ID")
    name = models.CharField(max_length=100, verbose_name="端末名")
    cpu_usage = models.FloatField(verbose_name="CPU使用率(%)")
    storage_usage = models.FloatField(verbose_name="ストレージ使用率(%)")
    
    NETWORK_CHOICES = (
        (0, '接続'),
        (1, '切断'),
    )
    network_status = models.IntegerField(choices=NETWORK_CHOICES, verbose_name="ネットワーク状態")
    checked_at = models.DateTimeField(verbose_name="確認日時")

    class Meta:
        db_table = 'device_info'
        verbose_name = '端末情報'

    def __str__(self):
        return f"{self.name} ({self.get_network_status_display()})"


# 4. カメラ情報テーブル (camera_info)
class CameraInfo(models.Model):
    camera_id = models.CharField(max_length=50, primary_key=True, verbose_name="カメラID")
    location = models.ForeignKey(
        LocationMaster, on_delete=models.CASCADE, db_column='location_id', verbose_name="場所ID"
    )
    device = models.ForeignKey(
        DeviceInfo, on_delete=models.CASCADE, db_column='device_id', verbose_name="端末ID"
    )
    name = models.CharField(max_length=100, verbose_name="カメラ名")
    
    TYPE_CHOICES = (
        (0, 'Raspberry Pi Camera'),
        (1, 'USB Webcam'),
        (2, 'IP Camera / RTSP'),
        (3, 'Video File (Test)'),
    )
    camera_type = models.IntegerField(choices=TYPE_CHOICES, verbose_name="カメラ種類")
    
    STATUS_CHOICES = (
        (0, '正常'),
        (1, '異常'),
        (2, '不通'),
    )
    status = models.IntegerField(choices=STATUS_CHOICES, verbose_name="稼働状態")
    installed_at = models.DateTimeField(verbose_name="設置日時")

    class Meta:
        db_table = 'camera_info'
        verbose_name = 'カメラ情報'

    def __str__(self):
        return f"{self.name} [{self.get_camera_type_display()}]"


# 5. 混雑状況記録テーブル (crowd_log)
class CrowdLog(models.Model):
    log_id = models.AutoField(primary_key=True, verbose_name="記録ID")
    location = models.ForeignKey(
        LocationMaster, on_delete=models.CASCADE, db_column='location_id', verbose_name="場所ID"
    )
    user_count = models.IntegerField(verbose_name="利用者数")
    crowd_rate = models.FloatField(verbose_name="混雑率(%)")
    recorded_at = models.DateTimeField(verbose_name="記録日時")

    class Meta:
        db_table = 'crowd_log'
        verbose_name = '混雑状況記録'


# 6. 混雑予測情報テーブル (crowd_prediction)
class CrowdPrediction(models.Model):
    prediction_id = models.AutoField(primary_key=True, verbose_name="予測ID")
    location = models.ForeignKey(
        LocationMaster, on_delete=models.CASCADE, db_column='location_id', verbose_name="場所ID"
    )
    expected_count = models.IntegerField(verbose_name="予測利用者数")
    predicted_at = models.DateTimeField(verbose_name="予測日時")

    class Meta:
        db_table = 'crowd_prediction'
        verbose_name = '混雑予測情報'


# 7. 週間集計ログテーブル (weekly_summary_log)
class WeeklySummaryLog(models.Model):
    weekly_log_id = models.AutoField(primary_key=True, verbose_name="週間集計ID")
    location = models.ForeignKey(
        LocationMaster, on_delete=models.CASCADE, db_column='location_id', verbose_name="場所ID"
    )
    start_at = models.DateTimeField(verbose_name="集計開始日時")
    end_at = models.DateTimeField(verbose_name="集計終了日時")
    avg_count = models.FloatField(verbose_name="平均利用者数")
    max_count = models.IntegerField(verbose_name="最大利用者数")
    executed_at = models.DateTimeField(verbose_name="集計実行日時")

    class Meta:
        db_table = 'weekly_summary_log'
        verbose_name = '週間集計ログ'


# 8. 曜日別集計ログテーブル (day_of_week_summary_log)
class DayOfWeekSummaryLog(models.Model):
    dow_log_id = models.AutoField(primary_key=True, verbose_name="曜日集計ID")
    location = models.ForeignKey(
        LocationMaster, on_delete=models.CASCADE, db_column='location_id', verbose_name="場所ID"
    )
    summary_month = models.DateTimeField(verbose_name="集計対象月")
    
    DOW_CHOICES = (
        (0, '日曜日'), (1, '月曜日'), (2, '火曜日'), 
        (3, '水曜日'), (4, '木曜日'), (5, '金曜日'), (6, '土曜日'),
    )
    day_of_week = models.IntegerField(choices=DOW_CHOICES, verbose_name="曜日")
    avg_count = models.FloatField(verbose_name="平均利用者数")
    executed_at = models.DateTimeField(verbose_name="集計実行日時")

    class Meta:
        db_table = 'day_of_week_summary_log'
        verbose_name = '曜日別集計ログ'


# 9. 月次レポートテーブル (monthly_report)
class MonthlyReport(models.Model):
    report_id = models.AutoField(primary_key=True, verbose_name="レポートID")
    location = models.ForeignKey(
        LocationMaster, on_delete=models.CASCADE, db_column='location_id', verbose_name="場所ID"
    )
    admin = models.ForeignKey(
        AdminInfo, on_delete=models.CASCADE, db_column='admin_id', verbose_name="管理者ID"
    )
    summary_month = models.DateTimeField(verbose_name="集計対象月")
    avg_utilization = models.FloatField(verbose_name="平均利用率(%)")
    max_users = models.IntegerField(verbose_name="最大利用者数")
    total_creations = models.IntegerField(default=1, verbose_name="総作成回数")

    class Meta:
        db_table = 'monthly_report'
        verbose_name = '月次レポート'