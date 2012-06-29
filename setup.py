from setuptools import setup, find_packages


setup(

    name = "QuickBooks",

    version = '0.1',

    packages = find_packages(),

    install_requires = ['requests', 'requests-oauth', 'lxml'],
    include_package_data = True,

    # metadata for upload to PyPI
    author = "Hans Kuder",
    author_email = "hans@hiidef.com",
    description = "Django Quickbooks App",
    license = "MIT License",
    keywords = "django quickbooks intuit",
    url = "http://github.com/hiidef/django-quickbooks",

)
