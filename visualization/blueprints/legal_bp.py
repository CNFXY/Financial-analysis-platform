# -*- coding: utf-8 -*-
"""合规与站点信息蓝图（公开，无需认证）。

提供站点级公开信息（站点名、运营主体、ICP/公安备案号、联系方式），
供前端页脚与「关于/备案」页展示。生产环境经 Nginx 反代 /api 可达。
"""
from flask import Blueprint, jsonify

from fund_estimation_system import config

bp = Blueprint('legal', __name__, url_prefix='/api/public')


@bp.route('/site-config', methods=['GET'])
def site_config():
    """返回站点公开配置（用于页脚备案号、关于页等）。"""
    return jsonify({
        'site_name': getattr(config, 'SITE_NAME', 'FUND-OS'),
        'company_name': getattr(config, 'COMPANY_NAME', ''),
        'icp_beian': getattr(config, 'ICP_BEIAN', ''),
        'police_beian': getattr(config, 'POLICE_BEIAN', ''),
        'contact_email': getattr(config, 'CONTACT_EMAIL', ''),
        'service_tel': getattr(config, 'SERVICE_TEL', ''),
    })
