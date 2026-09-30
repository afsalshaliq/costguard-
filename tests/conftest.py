import pytest


@pytest.fixture
def vm_items():
    return [
        {"priceType": "Consumption", "unitOfMeasure": "1 Hour", "productName": "Virtual Machines BS Series Spot", "meterName": "B2s Spot", "retailPrice": 0.002},
        {"priceType": "Consumption", "unitOfMeasure": "1 Hour", "productName": "Virtual Machines BS Series Low Priority", "meterName": "B2s Low Priority", "retailPrice": 0.003},
        {"priceType": "Consumption", "unitOfMeasure": "1 Hour", "productName": "Virtual Machines BS Series Windows", "meterName": "B2s Windows", "retailPrice": 0.0496},
        {"priceType": "Reservation", "unitOfMeasure": "1 Hour", "productName": "Virtual Machines BS Series", "meterName": "B2s Reservation", "retailPrice": 0.01},
        {"priceType": "Consumption", "unitOfMeasure": "1 Hour", "productName": "Virtual Machines BS Series", "meterName": "B2s", "retailPrice": 0.0416},
    ]


@pytest.fixture
def disk_items():
    return [
        {"priceType": "Consumption", "unitOfMeasure": "1/Month", "productName": "Premium Page Blob", "skuName": "P10 LRS", "meterName": "P10 LRS Disk", "retailPrice": 19.71},
        {"priceType": "Consumption", "unitOfMeasure": "1/Month", "productName": "Premium SSD Managed Disks", "skuName": "P10 LRS", "meterName": "P10 LRS Disk Mount", "retailPrice": 0.91},
        {"priceType": "Consumption", "unitOfMeasure": "1/Month", "productName": "Premium SSD Managed Disks", "skuName": "P10 LRS", "meterName": "P10 LRS Disk", "retailPrice": 19.71},
    ]