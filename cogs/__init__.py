from pkgutil import iter_modules

# gets all cog names (cogs.funny, cogs.general, etc.)
COGS = [module.name for module in iter_modules(__path__, f'{__package__}.')]