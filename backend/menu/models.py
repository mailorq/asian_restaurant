from django.db import models


class Ingredient(models.Model):
    name = models.CharField(max_length=80, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Product(models.Model):
    class Category(models.TextChoices):
        DISH = "dish", "Блюдо"
        DRINK = "drink", "Напиток"
        DESSERT = "dessert", "Десерт"

    category = models.CharField(max_length=10, choices=Category.choices, db_index=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    image = models.ImageField(upload_to="products/", blank=True)
    ingredients = models.ManyToManyField(Ingredient, related_name="products", blank=True)
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["category", "name"]
        indexes = [models.Index(fields=["category", "is_active"])]
        constraints = [
            models.CheckConstraint(check=models.Q(price__gte=0), name="product_price_gte_0"),
        ]

    def __str__(self) -> str:
        return self.name
