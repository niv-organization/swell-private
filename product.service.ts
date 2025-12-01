type Product = {
  id: string;
  slug: string;
  category: string;
  description: string;
};

type ProductInput = {
  productId: string;
  productSlug?: string;
  categorySlug?: string;
  productDescription?: string;
};

export class ProductService {
  createProduct(input: ProductInput): Product {
    const product: Product = {
      id: input.productId,
      slug: input.productSlug ?? '',
      category: input.categorySlug ?? '',
      description: input.productDescription ?? '',
    };
    return product;
  }
}
