"""Download the small Apache-2.0 Vosk model, confined to this project's models directory."""
import shutil
import tempfile
from pathlib import Path
from urllib.request import urlopen
from zipfile import ZipFile
from .audio import MODEL_PATH


def main():
    if (MODEL_PATH / 'am/final.mdl').is_file():
        print('Wake model is already installed.')
        return
    target = MODEL_PATH.parent.resolve()
    target.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target) as folder:
        archive = Path(folder) / 'model.zip'
        print('Downloading the local wake model (~40 MB)…')
        with urlopen('https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip', timeout=60) as source:
            with archive.open('wb') as dest:
                shutil.copyfileobj(source, dest)
        with ZipFile(archive) as bundle:
            root = Path(folder).resolve()
            for member in bundle.infolist():
                if not (root / member.filename).resolve().is_relative_to(root):
                    raise ValueError('Unsafe model archive path.')
            bundle.extractall(root)
        source = root / MODEL_PATH.name
        if not (source / 'am/final.mdl').is_file():
            raise ValueError('Downloaded model is incomplete.')
        if MODEL_PATH.exists():
            raise RuntimeError('Incomplete model folder exists. Rename it before retrying.')
        shutil.move(str(source), str(MODEL_PATH))
    print('Wake model ready.')


if __name__ == '__main__':
    main()
