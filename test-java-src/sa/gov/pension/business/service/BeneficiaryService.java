package sa.gov.pension.business.service;

public class BeneficiaryService {

    public void removeBeneficiary(String beneficiaryId) {
        checkPermissions(beneficiaryId);
        deleteFromDatabase(beneficiaryId);
    }

    private void checkPermissions(String beneficiaryId) {
        // Verify the caller has permission to remove this beneficiary
        if (beneficiaryId.startsWith("ADMIN")) {
            throw new SecurityException("Cannot remove admin beneficiaries");
        }
    }

    private void deleteFromDatabase(String beneficiaryId) {
        System.out.println("Deleting beneficiary " + beneficiaryId + " from database");
    }
}
