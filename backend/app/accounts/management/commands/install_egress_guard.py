# -*- coding: utf-8 -*-
import json
from pathlib import Path
from urllib.parse import urlsplit

from django.core.management.base import BaseCommand, CommandError
from rest_framework.exceptions import ValidationError

from app.utils import req_gateway

GUARD_NAME = "外联泄漏防护"
GUARD_MARKER = "__MIRROR_EGRESS_GUARD__"
GUARD_TEMPLATE = Path(__file__).resolve().parents[2] / "egress_guard.js"
TRUSTED_HOST_PLACEHOLDER = "__MIRROR_TRUSTED_HOSTS__"


def trusted_hosts(sources):
    hosts = []
    for source in sources or []:
        try:
            host = urlsplit(str(source)).hostname
        except ValueError:
            host = None
        if host:
            hosts.append(host)
    return hosts


def build_guard_content(extra_hosts):
    try:
        template = GUARD_TEMPLATE.read_text(encoding="utf-8")
    except OSError:
        raise CommandError(f"找不到注入脚本模板: {GUARD_TEMPLATE}")
    if TRUSTED_HOST_PLACEHOLDER not in template:
        raise CommandError("注入脚本模板缺少可信域名占位符")
    hosts = sorted({host.lower() for host in extra_hosts if host})
    return template.replace(TRUSTED_HOST_PLACEHOLDER, json.dumps(hosts))


def find_guard(scripts):
    for index, script in enumerate(scripts):
        if GUARD_MARKER in str(script.get("content") or ""):
            return index
    return None


class Command(BaseCommand):
    help = "通过网关自定义脚本机制安装/移除浏览器外联泄漏防护（egress guard）"

    def add_arguments(self, parser):
        parser.add_argument("--remove", action="store_true", help="移除已安装的外联防护脚本")
        parser.add_argument("--dry-run", action="store_true", help="只显示将要执行的变更，不写回网关")
        parser.add_argument("--allow-host", action="append", default=[], metavar="HOST",
                            help="额外放行的域名，可重复指定；默认并入脚本管理中的可信 CDN 源")

    def handle(self, *args, **options):
        try:
            config = req_gateway("get", "/api/custom-scripts")
        except ValidationError as exc:
            raise CommandError(f"读取网关脚本配置失败: {exc.detail}")

        scripts = [dict(script) for script in (config.get("scripts") or [])]
        trusted_sources = list(config.get("trusted_cdn_sources") or [])
        guard_index = find_guard(scripts)

        if options["remove"]:
            if guard_index is None:
                self.stdout.write("网关中没有已安装的外联防护脚本")
                return
            removed = scripts.pop(guard_index)
            if not options["dry_run"]:
                try:
                    req_gateway("post", "/api/custom-scripts", json={
                        "scripts": scripts,
                        "trusted_cdn_sources": trusted_sources,
                    })
                except ValidationError as exc:
                    raise CommandError(f"写回网关脚本配置失败: {exc.detail}")
            self.stdout.write(self.style.SUCCESS(
                f"已移除外联防护脚本 (id={removed.get('id')})，其余脚本与可信 CDN 源保持不变"))
            return

        extra_hosts = trusted_hosts(trusted_sources) + list(options["allow_host"])
        content = build_guard_content(extra_hosts)
        script = {
            "id": 0,
            "enabled": True,
            "name": GUARD_NAME,
            "language": "javascript",
            "position": "head_start",
            "content": content,
        }
        if guard_index is not None:
            script["id"] = scripts[guard_index].get("id") or 0
            scripts[guard_index] = script
            action = "已更新"
        else:
            script["id"] = max([int(s.get("id") or 0) for s in scripts] + [0]) + 1
            scripts.append(script)
            action = "已安装"

        if options["dry_run"]:
            self.stdout.write(f"[dry-run] {action}外联防护脚本 id={script['id']}，"
                              f"放行域名: {', '.join(sorted(set(extra_hosts))) or '无'}")
            return

        try:
            req_gateway("post", "/api/custom-scripts", json={
                "scripts": scripts,
                "trusted_cdn_sources": trusted_sources,
            })
        except ValidationError as exc:
            raise CommandError(f"写回网关脚本配置失败: {exc.detail}")

        self.stdout.write(self.style.SUCCESS(
            f"{action}外联防护脚本 (id={script['id']})，"
            f"放行域名: challenges.cloudflare.com"
            + (f"、{', '.join(sorted(set(extra_hosts)))}" if extra_hosts else "")))
        self.stdout.write("被拦截的外联请求会记录在 访问日志 → 外联拦截；"
                          "修改可信 CDN 源后请重新执行本命令同步白名单")
