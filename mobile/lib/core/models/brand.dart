/// One input of a dynamic pairing form.
class FormFieldSpec {
  const FormFieldSpec({
    required this.name,
    required this.label,
    this.type = 'text',
    this.required = true,
    this.placeholder,
    this.options = const [],
    this.defaultValue,
    this.help,
  });

  final String name;
  final String label;
  final String type; // text|password|number|select|qr|toggle|textarea
  final bool required;
  final String? placeholder;
  final List<({String value, String label})> options;
  final dynamic defaultValue;
  final String? help;

  factory FormFieldSpec.fromJson(Map<String, dynamic> json) => FormFieldSpec(
        name: json['name'] as String,
        label: (json['label'] as String?) ?? json['name'] as String,
        type: (json['type'] as String?) ?? 'text',
        required: json['required'] != false,
        placeholder: json['placeholder'] as String?,
        options: (json['options'] as List?)
                ?.whereType<Map>()
                .map((o) => (value: o['value'].toString(), label: (o['label'] ?? o['value']).toString()))
                .toList() ??
            const [],
        defaultValue: json['default'],
        help: json['help'] as String?,
      );
}

class PairingMethod {
  const PairingMethod({
    required this.id,
    required this.title,
    this.description = '',
    this.fields = const [],
    this.supportsDiscovery = false,
    this.requiresIntegration = false,
    this.icon,
  });

  final String id;
  final String title;
  final String description;
  final List<FormFieldSpec> fields;
  final bool supportsDiscovery;
  final bool requiresIntegration;
  final String? icon;

  factory PairingMethod.fromJson(Map<String, dynamic> json) => PairingMethod(
        id: json['id'] as String,
        title: (json['title'] as String?) ?? json['id'] as String,
        description: (json['description'] as String?) ?? '',
        fields: (json['fields'] as List?)?.whereType<Map>().map((e) => FormFieldSpec.fromJson(Map<String, dynamic>.from(e))).toList() ?? const [],
        supportsDiscovery: json['supports_discovery'] == true,
        requiresIntegration: json['requires_integration'] == true,
        icon: json['icon'] as String?,
      );
}

class BrandInfo {
  const BrandInfo({
    required this.id,
    required this.name,
    this.vendor = '',
    this.description = '',
    this.protocols = const [],
    this.categories = const [],
    this.methods = const [],
    this.icon = 'devices',
    this.docsUrl = '',
    this.color = '#2563EB',
  });

  final String id;
  final String name;
  final String vendor;
  final String description;
  final List<String> protocols;
  final List<String> categories;
  final List<PairingMethod> methods;
  final String icon;
  final String docsUrl;
  final String color;

  factory BrandInfo.fromJson(Map<String, dynamic> json) => BrandInfo(
        id: json['id'] as String,
        name: (json['name'] as String?) ?? json['id'] as String,
        vendor: (json['vendor'] as String?) ?? '',
        description: (json['description'] as String?) ?? '',
        protocols: (json['protocols'] as List?)?.map((e) => e.toString()).toList() ?? const [],
        categories: (json['categories'] as List?)?.map((e) => e.toString()).toList() ?? const [],
        methods: (json['methods'] as List?)?.whereType<Map>().map((e) => PairingMethod.fromJson(Map<String, dynamic>.from(e))).toList() ?? const [],
        icon: (json['icon'] as String?) ?? 'devices',
        docsUrl: (json['docs_url'] as String?) ?? '',
        color: (json['color'] as String?) ?? '#2563EB',
      );

  PairingMethod? method(String id) {
    for (final m in methods) {
      if (m.id == id) return m;
    }
    return null;
  }
}

class DiscoveredDevice {
  const DiscoveredDevice({required this.externalId, required this.name, this.category = 'generic', this.model, this.manufacturer, this.address, this.extra = const {}});

  final String externalId;
  final String name;
  final String category;
  final String? model;
  final String? manufacturer;
  final String? address;
  final Map<String, dynamic> extra;

  factory DiscoveredDevice.fromJson(Map<String, dynamic> json) => DiscoveredDevice(
        externalId: json['external_id'] as String,
        name: (json['name'] as String?) ?? '',
        category: (json['category'] as String?) ?? 'generic',
        model: json['model'] as String?,
        manufacturer: json['manufacturer'] as String?,
        address: json['address'] as String?,
        extra: Map<String, dynamic>.from((json['extra'] as Map?) ?? const {}),
      );
}

class ParsedCode {
  const ParsedCode({required this.kind, this.brand, this.method, this.data = const {}});

  final String kind; // matter_qr | matter_manual | tuya_qr | url | unknown
  final String? brand;
  final String? method;
  final Map<String, dynamic> data;

  bool get isKnown => kind != 'unknown';

  factory ParsedCode.fromJson(Map<String, dynamic> json) => ParsedCode(
        kind: (json['kind'] as String?) ?? 'unknown',
        brand: json['brand'] as String?,
        method: json['method'] as String?,
        data: Map<String, dynamic>.from((json['data'] as Map?) ?? const {}),
      );
}

class DeviceCategoryInfo {
  const DeviceCategoryInfo({required this.id, required this.name, required this.nameEn, required this.icon, required this.group, this.brands = const []});

  final String id;
  final String name;
  final String nameEn;
  final String icon;
  final String group;
  final List<String> brands;

  factory DeviceCategoryInfo.fromJson(Map<String, dynamic> json) => DeviceCategoryInfo(
        id: json['id'] as String,
        name: (json['name'] as String?) ?? json['id'] as String,
        nameEn: (json['name_en'] as String?) ?? json['id'] as String,
        icon: (json['icon'] as String?) ?? 'devices',
        group: (json['group'] as String?) ?? 'other',
        brands: (json['brands'] as List?)?.map((e) => e.toString()).toList() ?? const [],
      );
}

class CategoryGroup {
  const CategoryGroup({required this.id, required this.name, required this.nameEn, required this.icon, this.categories = const []});

  final String id;
  final String name;
  final String nameEn;
  final String icon;
  final List<DeviceCategoryInfo> categories;

  factory CategoryGroup.fromJson(Map<String, dynamic> json) => CategoryGroup(
        id: json['id'] as String,
        name: (json['name'] as String?) ?? json['id'] as String,
        nameEn: (json['name_en'] as String?) ?? json['id'] as String,
        icon: (json['icon'] as String?) ?? 'devices',
        categories: (json['categories'] as List?)?.whereType<Map>().map((e) => DeviceCategoryInfo.fromJson(Map<String, dynamic>.from(e))).toList() ?? const [],
      );
}
