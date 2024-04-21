import os, inspect
from importlib import import_module
from django.core.exceptions import ImproperlyConfigured
from django.utils.functional import cached_property
from django.utils.module_loading import import_string, module_has_submodule

APPS_MODULE_NAME, MODELS_MODULE_NAME = "apps", "models"

class AppConfig:
    def __init__(self, app_name, app_module):
        self.name, self.module, self.apps = app_name, app_module, None
        self.label = app_name.rpartition(".")[2]
        if not hasattr(self, "label"):
            self.label = app_name.rpartition(".")[2]
        if not self.label.isidentifier():
            raise ImproperlyConfigured(f"The app label '{self.label}' is not a valid Python identifier.")
        self.verbose_name = self.label.title()
        self.path, self.models_module, self.models = None, None, None

    def __repr__(self):
        return f"<{self.__class__.__name__}: {self.label}>"

    @cached_property
    def default_auto_field(self):
        from django.conf import settings
        return settings.DEFAULT_AUTO_FIELD

    @property
    def _is_default_auto_field_overridden(self):
        return self.__class__.default_auto_field is not AppConfig.default_auto_field

    def _path_from_module(self, module):
        paths = list(getattr(module, "__path__", []))
        if len(paths) != 1:
            filename = getattr(module, "__file__", None)
            if filename is not None:
                paths = [os.path.dirname(filename)]
            else:
                paths = list(set(paths))
        if len(paths) > 1:
            raise ImproperlyConfigured(f"The app module {repr(module)} has multiple filesystem locations ({paths}); you must configure this app with an AppConfig subclass with a 'path' class attribute.")
        elif not paths:
            raise ImproperlyConfigured(f"The app module {repr(module)} has no filesystem location; you must configure this app with an AppConfig subclass with a 'path' class attribute.")
        return paths[0]

    @classmethod
    def create(cls, entry):
        app_config_class, app_name, app_module = None, None, None
        try:
            app_module = import_module(entry)
        except Exception:
            pass
        else:
            if module_has_submodule(app_module, APPS_MODULE_NAME):
                mod_path = f"{entry}.{APPS_MODULE_NAME}"
                mod = import_module(mod_path)
                app_configs = [(name, candidate) for name, candidate in inspect.getmembers(mod, inspect.isclass)
                               if issubclass(candidate, cls) and candidate is not cls and getattr(candidate, "default", True)]
                if len(app_configs) == 1:
                    app_config_class = app_configs[0][1]
                else:
                    app_configs = [(name, candidate) for name, candidate in app_configs
                                   if getattr(candidate, "default", False)]
                    if len(app_configs) > 1:
                        candidates = [repr(name) for name, _ in app_configs]
                        raise RuntimeError(f"{mod_path} declares more than one default AppConfig: {', '.join(candidates)}")
                    elif len(app_configs) == 1:
                        app_config_class = app_configs[0][1]
            if app_config_class is None:
                app_config_class = cls
                app_name = entry

        if app_config_class is None:
            try:
                app_config_class = import_string(entry)
            except Exception:
                pass

        if app_module is None and app_config_class is None:
            mod_path, _, cls_name = entry.rpartition(".")
            if mod_path and cls_name[0].isupper():
                mod = import_module(mod_path)
                candidates = [repr(name) for name, candidate in inspect.getmembers(mod, inspect.isclass)
                               if issubclass(candidate, cls) and candidate is not cls]
                msg = f"Module '{mod_path}' does not contain a '{cls_name}' class."
                if candidates:
                    msg += f" Choices are: {', '.join(candidates)}."
                raise ImportError(msg)
            else:
                import_module(entry)

        if not issubclass(app_config_class, AppConfig):
            raise ImproperlyConfigured(f"'{entry}' isn't a subclass of AppConfig.")

        if app_name is None:
            try:
                app_name = app_config_class.name
            except AttributeError:
                raise ImproperlyConfigured(f"'{entry}' must supply a name attribute.")

        try:
            app_module = import_module(app_name)
        except ImportError:
            raise ImproperlyConfigured(
                f"Cannot import '{app_name}'. Check that '{app_config_class.__module__}.{app_config_class.__qualname__}.name' is correct."
            )

        return app_config_class(app_name, app_module)

    def get_model(self, model_name, require_ready=True):
        if require_ready:
            self.apps.check_models_ready()
        else:
            self.apps.check_apps_ready()
        try:
            return self.models[model_name.lower()]
        except KeyError:
            raise LookupError(f"App '{self.label}' doesn't have a '{model_name}' model.")

    def get_models(self, include_auto_created=False, include_swapped=False):
        self.apps.check_models_ready()
        for model in self.models.values():
            if model._meta.auto_created and not include_auto_created:
                continue
            if model._meta.swapped and not include_swapped:
                continue
            yield model

    def import_models(self):
        self.models = self.apps.all_models[self.label]
        if module_has_submodule(self.module, MODELS_MODULE_NAME):
            models_module_name = f"{self.name}.{MODELS_MODULE_NAME}"
            self.models_module = import_module(models_module_name)

    def ready(self):
        pass
