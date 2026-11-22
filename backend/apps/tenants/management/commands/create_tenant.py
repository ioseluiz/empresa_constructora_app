from getpass import getpass
from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from apps.accounts.models import User
from apps.tenants.services import create_tenant


class Command(BaseCommand):
    help = "Crea una empresa (tenant) y su usuario administrador."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--name", required=True, help="Nombre comercial")
        parser.add_argument("--owner-email", required=True)
        parser.add_argument("--owner-password", help="Si se omite y el usuario no existe, se pide")
        parser.add_argument("--slug")
        parser.add_argument("--ruc", default="")
        parser.add_argument("--dv", default="")

    def handle(self, *args: Any, **opts: Any) -> None:
        password = opts["owner_password"]
        if not password and not User.objects.filter(email__iexact=opts["owner_email"]).exists():
            password = getpass("Contraseña del administrador: ")
        tenant, owner = create_tenant(
            name=opts["name"],
            owner_email=opts["owner_email"],
            owner_password=password,
            slug=opts["slug"],
            ruc=opts["ruc"],
            dv=opts["dv"],
        )
        self.stdout.write(
            self.style.SUCCESS(f"Empresa '{tenant}' ({tenant.pk}) creada; admin: {owner}")
        )
