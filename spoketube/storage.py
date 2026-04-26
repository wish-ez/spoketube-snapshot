from django.core.files.storage import get_storage_class
from storages.backends.s3boto3 import S3Boto3Storage
from os.path import splitext

class CachedS3Boto3Storage(S3Boto3Storage):
    """
    S3 storage backend that saves the files locally, too.
    """
    def __init__(self, *args, **kwargs):
        super(CachedS3Boto3Storage, self).__init__(*args, **kwargs)
        self.local_storage = get_storage_class(
            "compressor.storage.CompressorFileStorage")()

    def save(self, name, content):
        self.local_storage._save(name, content)
        super(CachedS3Boto3Storage, self).save(name, self.local_storage._open(name))
        return name

class StaticToS3Storage(S3Boto3Storage):

    def __init__(self, *args, **kwargs):
        super(StaticToS3Storage, self).__init__(*args, **kwargs)
        self.local_storage = get_storage_class('compressor.storage.CompressorFileStorage')()

    def save(self, name, content):
        ext = splitext(name)[1]
        parent_dir = name.split('/')[0]
        if ext in ['.css', '.js'] and not parent_dir == 'admin':
            self.local_storage._save(name, content)
        else:
            filename = super(StaticToS3Storage, self).save(name, content)
            return filename