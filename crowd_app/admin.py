from django.contrib import admin
from .models import (
    AdminInfo, LocationMaster, DeviceInfo, CameraInfo, 
    CrowdLog, CrowdPrediction, WeeklySummaryLog, 
    DayOfWeekSummaryLog, MonthlyReport
)

admin.site.register(AdminInfo)
admin.site.register(LocationMaster)
admin.site.register(DeviceInfo)
admin.site.register(CameraInfo)
admin.site.register(CrowdLog)
admin.site.register(CrowdPrediction)
admin.site.register(WeeklySummaryLog)
admin.site.register(DayOfWeekSummaryLog)
admin.site.register(MonthlyReport)