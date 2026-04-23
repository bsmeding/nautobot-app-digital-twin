"""Django API urlpatterns declaration for nautobot_digital_twin app."""

from nautobot.apps.api import OrderedDefaultRouter

from nautobot_digital_twin.api import views

router = OrderedDefaultRouter()
# add the name of your api endpoint, usually hyphenated model name in plural, e.g. "my-model-classes"
router.register("nautobot-app-digital-twin-example-models", views.NautobotDigitalTwinExampleModelViewSet)
router.register("digital-twin-deployments", views.DigitalTwinDeploymentViewSet)

app_name = "nautobot_digital_twin-api"
urlpatterns = router.urls
