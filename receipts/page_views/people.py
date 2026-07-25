from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render

from ..models import Person


AVATAR_PRESETS = [
    {
        "value": value,
        "filename": f"avatar-{value.removeprefix('preset-')}.svg",
        "static_path": f"images/avatars/avatar-{value.removeprefix('preset-')}.svg",
        "label": label,
    }
    for value, label in Person.AVATAR_CHOICES
    if value.startswith("preset-")
]


def _has_supported_image_signature(upload):
    header = upload.read(16)
    upload.seek(0)
    return (
        header.startswith(b"\x89PNG\r\n\x1a\n")
        or header.startswith(b"\xff\xd8\xff")
        or header.startswith((b"GIF87a", b"GIF89a"))
        or (header.startswith(b"RIFF") and header[8:12] == b"WEBP")
    )


def people(request):
    if request.method == "POST":
        if request.POST.get("delete_person"):
            person = get_object_or_404(Person, pk=request.POST.get("delete_person"))
            person.active = False
            person.is_deleted = True
            person.save()
            messages.success(request, "Person wurde gelöscht. Bestehende Zuordnungen bleiben erhalten.")
            return redirect("receipts:people")

        action = request.POST.get("action")
        if action == "add":
            name = request.POST.get("name", "").strip()
            if not name:
                messages.error(request, "Name fehlt.")
            else:
                try:
                    person, created = Person.objects.get_or_create(
                        name=name,
                        defaults={"active": True, "is_deleted": False},
                    )
                    if created:
                        messages.success(request, "Person wurde angelegt.")
                    elif person.is_deleted:
                        person.active = True
                        person.is_deleted = False
                        person.save()
                        messages.success(request, "Person wurde wiederhergestellt.")
                    else:
                        messages.error(request, "Diese Person existiert bereits.")
                except IntegrityError:
                    messages.error(request, "Diese Person existiert bereits.")
        elif action == "save":
            try:
                with transaction.atomic():
                    used_presets = {
                        person.avatar_choice: person.name
                        for person in Person.objects.filter(
                            is_deleted=True, avatar_choice__startswith="preset-"
                        )
                    }
                    for person in Person.objects.filter(is_deleted=False):
                        new_name = request.POST.get(f"name-{person.id}", "").strip()
                        if new_name:
                            person.name = new_name
                        person.active = request.POST.get(f"active-{person.id}") == "on"
                        avatar_choice = request.POST.get(f"avatar-choice-{person.id}", "initials")
                        valid_avatar_choices = {value for value, _label in Person.AVATAR_CHOICES}
                        if avatar_choice not in valid_avatar_choices:
                            avatar_choice = "initials"
                        if avatar_choice.startswith("preset-"):
                            if avatar_choice in used_presets:
                                raise ValidationError(
                                    f"Das Tieravatar ist bereits für {used_presets[avatar_choice]} ausgewählt."
                                )
                            used_presets[avatar_choice] = person.name
                        avatar_upload = request.FILES.get(f"avatar-upload-{person.id}")
                        if avatar_upload:
                            if avatar_upload.size > 5 * 1024 * 1024:
                                raise ValidationError(f"Avatar für {person.name} darf maximal 5 MB groß sein.")
                            if avatar_upload.content_type not in {
                                "image/png", "image/jpeg", "image/gif", "image/webp"
                            }:
                                raise ValidationError(f"Avatar für {person.name} muss PNG, JPG, GIF oder WebP sein.")
                            if not _has_supported_image_signature(avatar_upload):
                                raise ValidationError(f"Avatar für {person.name} enthält keine gültigen Bilddaten.")
                            Person._meta.get_field("avatar_upload").run_validators(avatar_upload)
                            previous_upload = person.avatar_upload.name
                            person.avatar_upload = avatar_upload
                            avatar_choice = "upload"
                            if previous_upload:
                                storage = person.avatar_upload.storage
                                transaction.on_commit(
                                    lambda name=previous_upload, file_storage=storage: file_storage.delete(name)
                                )
                        if avatar_choice == "upload" and not person.avatar_upload:
                            raise ValidationError(f"Für {person.name} wurde noch kein eigenes Avatarbild hochgeladen.")
                        person.avatar_choice = avatar_choice
                        person.save()
                messages.success(request, "Personen wurden gespeichert.")
            except IntegrityError:
                messages.error(request, "Personennamen und Tieravatare müssen eindeutig sein.")
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
        elif action == "delete":
            person = get_object_or_404(Person, pk=request.POST.get("person_id"))
            person.active = False
            person.is_deleted = True
            person.save()
            messages.success(request, "Person wurde gelöscht. Bestehende Zuordnungen bleiben erhalten.")
        elif action == "restore":
            person = get_object_or_404(Person, pk=request.POST.get("person_id"))
            person.active = True
            person.is_deleted = False
            person.save()
            messages.success(request, "Person wurde wiederhergestellt.")
        elif action == "hard_delete":
            person = get_object_or_404(Person, pk=request.POST.get("person_id"), is_deleted=True)
            try:
                avatar_name = person.avatar_upload.name
                avatar_storage = person.avatar_upload.storage
                person.delete()
                if avatar_name:
                    avatar_storage.delete(avatar_name)
                messages.success(request, "Person wurde endgültig gelöscht.")
            except ProtectedError:
                messages.error(
                    request,
                    "Person kann nicht endgültig gelöscht werden, weil sie noch in Belegen oder Zuordnungen verwendet wird.",
                )
        return redirect("receipts:people")
    preset_owners = {
        person.avatar_choice: person
        for person in Person.objects.filter(avatar_choice__startswith="preset-")
    }
    avatar_presets = [
        {
            **preset,
            "owner_id": preset_owners[preset["value"]].id if preset["value"] in preset_owners else None,
            "owner_name": preset_owners[preset["value"]].name if preset["value"] in preset_owners else "",
        }
        for preset in AVATAR_PRESETS
    ]
    return render(
        request,
        "receipts/people.html",
        {
            "active_people": Person.objects.filter(is_deleted=False),
            "avatar_presets": avatar_presets,
            "deleted_people": Person.objects.filter(is_deleted=True),
        },
    )
