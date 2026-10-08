from django.contrib import admin
from django import forms
admin.site.index_template = 'admin/prototype_index.html'
admin.site.login_template = 'crowd_app/management_login.html'
admin.site.site_header = 'Lynx-eyed 管理者ページ'
admin.site.site_title = 'Lynx-eyed'
from .models import (
    AdminInfo, LocationMaster, DeviceInfo, CameraInfo, 
    CrowdLog, CrowdPrediction, WeeklySummaryLog, 
    DayOfWeekSummaryLog, MonthlyReport
)

admin.site.register(AdminInfo)
admin.site.register(LocationMaster)
admin.site.register(DeviceInfo)
admin.site.register(CameraInfo)
class CrowdLogAdminForm(forms.ModelForm):
    user_count = forms.IntegerField(
        label="利用者数",
        min_value=0,
        error_messages={"min_value": "利用者人数は0以上で入力してください。"},
        help_text="0以上の人数を入力してください。",
    )

    class Meta:
        model = CrowdLog
        fields = "__all__"


@admin.register(CrowdLog)
class CrowdLogAdmin(admin.ModelAdmin):
    form = CrowdLogAdminForm
    readonly_fields = ('calculated_rate',)

    @admin.display(description="保存時の混雑率")
    def calculated_rate(self, obj):
        if obj is None:
            return "人数と場所から保存時に自動計算します。"
        return "算出不可" if obj.crowd_rate is None else f"{obj.crowd_rate:g}%"

admin.site.register(CrowdPrediction)
admin.site.register(WeeklySummaryLog)
admin.site.register(DayOfWeekSummaryLog)
admin.site.register(MonthlyReport)
